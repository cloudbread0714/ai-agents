"""Folder check before completion (contracts/cli.md verify, data-model §5, §7).

Artifacts (FR-010), analysis.md and job.md format, base copies vs ``meta.sources``, and the
provenance check: numbers, Latin tech tokens and "부족한 점" keywords that appear in
resume.md or the result deck but not in the base originals.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pptx import Presentation

from job_apply import sources
from job_apply.errors import PlanError
from job_apply.models import Meta, TailorPlan, load_plan
from job_apply.pptx_dump import all_text, dump

ARTIFACTS = (
    "meta.json",
    "job.md",
    "analysis.md",
    "tailor.json",
    "resume.md",
    "resume.pdf",
    "portfolio.pptx",
    "portfolio.pdf",
    "changes.md",
    "base/resume.pdf",
    "base/resume.txt",
    "base/portfolio.pptx",
    "base/portfolio.json",
)
JOB_SECTIONS = (
    "## 요약",
    "## 자격 요건",
    "## 우대 사항",
    "## 주요 업무",
    "## 기타(근무지·형태·전형)",
)
ANALYSIS_SECTIONS = ("## 적합도 근거", "## 일치하는 점", "## 부족한 점", "## 지원 전 보완 제안")
GAP_STOPWORDS = {
    "경험",
    "부족",
    "없음",
    "없다",
    "필요",
    "부족함",
    "요건",
    "우대",
    "관련",
    "이상",
    "수준",
}
JOSA = re.compile(r"(은|는|이|가|을|를|의|에|에서|으로|로|과|와|도|만)$")

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*%?")
_LATIN = re.compile(r"[A-Za-z][A-Za-z0-9+#.]*[A-Za-z0-9+#]|[A-Za-z]{2,}")
_HANGUL = re.compile(r"[가-힣]{2,}")
_LIST_MARK = re.compile(r"^\s*\d+[.)]\s+", re.M)
_FRONT = re.compile(r"\A---\n(.*?)\n---\n?", re.S)


@dataclass
class VerifyResult:
    ok: bool = True
    missing: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    unresolved: list[dict[str, str]] = field(default_factory=list)
    acknowledged: list[dict[str, str]] = field(default_factory=list)
    fit_score: int | None = None
    summary: str | None = None

    def json(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("summary")
        return data


def h2(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.startswith("## ")]


def section(text: str, heading: str) -> str:
    lines, inside = [], False
    for ln in text.splitlines():
        if ln.startswith("## "):
            inside = ln.strip() == heading
            continue
        if inside:
            lines.append(ln)
    return "\n".join(lines).strip()


def read_analysis(path: Path, result: VerifyResult) -> str:
    text = path.read_text(encoding="utf-8")
    match = _FRONT.match(text)
    front: dict[str, Any] = {}
    if match:
        try:
            front = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            result.problems.append("analysis.md: frontmatter YAML 오류")
    score = front.get("fit_score")
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
        result.problems.append("analysis.md: fit_score는 0~100 정수여야 해요")
    else:
        result.fit_score = score
    if not str(front.get("summary") or "").strip():
        result.problems.append("analysis.md: summary가 필요해요")
    else:
        result.summary = str(front["summary"]).strip()
    if tuple(h2(text)) != ANALYSIS_SECTIONS:
        result.problems.append(
            "analysis.md: 섹션은 " + ", ".join(ANALYSIS_SECTIONS) + " 순서여야 해요"
        )
    return text


def _in(corpus: str, token: str) -> bool:
    if token[0].isdigit():
        bare = token.rstrip("%")
        pattern = rf"(?<![\d.]){re.escape(bare)}(?![\d])" + (r"\s*%" if token.endswith("%") else "")
        return re.search(pattern, corpus) is not None
    # A digit may come before: units are written glued to numbers ("30km", "512MB").
    return re.search(rf"(?<![a-z]){re.escape(token.lower())}(?![a-z0-9])", corpus) is not None


def gap_keywords(analysis: str, corpus: str) -> set[str]:
    gap = section(analysis, "## 부족한 점")
    words = {w.rstrip(".") for w in _LATIN.findall(gap)}
    words |= {JOSA.sub("", w) for w in _HANGUL.findall(gap)}
    return {w for w in words if len(w) >= 2 and w not in GAP_STOPWORDS and w.lower() not in corpus}


def provenance(outputs: dict[str, str], corpus: str, gaps: set[str]) -> list[dict[str, str]]:
    warnings: dict[tuple[str, str], dict[str, str]] = {}
    for file, text in outputs.items():
        text = _LIST_MARK.sub("", text)
        lowered = text.lower()
        for token in _NUMBER.findall(text):
            if not _in(corpus, token):
                warnings.setdefault((file, token), {"file": file, "token": token, "kind": "number"})
        for token in (t.rstrip(".") for t in _LATIN.findall(text)):
            if len(token) >= 2 and not _in(corpus, token):
                warnings.setdefault(
                    (file, token.lower()), {"file": file, "token": token, "kind": "tech"}
                )
        for word in gaps:
            if word.lower() in lowered:
                warnings[(file, word.lower())] = {"file": file, "token": word, "kind": "gap"}
    return list(warnings.values())


def split_acknowledged(warnings, plan: TailorPlan | None):
    notes = {(a.file, a.token.lower()): a for a in (plan.acknowledged_warnings if plan else [])}
    unresolved, acknowledged = [], []
    for w in warnings:
        note = notes.get((w["file"], w["token"].lower()))
        if note:
            acknowledged.append({**w, "source": note.source, "reason": note.reason})
        else:
            unresolved.append(w)
    return unresolved, acknowledged


def verify(folder: Path, meta: Meta) -> tuple[VerifyResult, TailorPlan | None]:
    result = VerifyResult()
    result.missing = [a for a in ARTIFACTS if not (folder / a).is_file()]
    if not (folder / "base" / "render").is_dir():
        result.missing.append("base/render/")
    base = folder / "base"
    for name, info in (
        ("resume.pdf", meta.sources.resume),
        ("portfolio.pptx", meta.sources.portfolio),
    ):
        if (base / name).is_file() and sources.sha256(base / name) != info.sha256:
            result.problems.append(f"base/{name}: meta.sources와 해시가 달라요")

    job = folder / "job.md"
    if job.is_file():
        heads = h2(job.read_text(encoding="utf-8"))
        absent = [s for s in JOB_SECTIONS if s not in heads]
        if absent:
            result.problems.append("job.md: 섹션이 없어요: " + ", ".join(absent))
    analysis = (
        read_analysis(folder / "analysis.md", result) if (folder / "analysis.md").is_file() else ""
    )

    plan = None
    base_dump = None
    if (base / "portfolio.json").is_file():
        base_dump = json.loads((base / "portfolio.json").read_text(encoding="utf-8"))
        if (folder / "tailor.json").is_file():
            try:
                plan = load_plan(folder / "tailor.json", base_dump["slide_count"])
            except PlanError as exc:
                result.problems.append(str(exc))

    corpus_parts = []
    if (base / "resume.txt").is_file():
        corpus_parts.append((base / "resume.txt").read_text(encoding="utf-8"))
    if base_dump:
        corpus_parts += all_text(base_dump)
    corpus = "\n".join(corpus_parts).lower()
    outputs = {}
    if (folder / "resume.md").is_file():
        outputs["resume.md"] = (folder / "resume.md").read_text(encoding="utf-8")
    if (folder / "portfolio.pptx").is_file():
        outputs["portfolio.pptx"] = "\n".join(
            all_text(dump(Presentation(str(folder / "portfolio.pptx"))))
        )
    warnings = provenance(outputs, corpus, gap_keywords(analysis, corpus) if analysis else set())
    result.unresolved, result.acknowledged = split_acknowledged(warnings, plan)
    result.ok = not result.missing and not result.problems
    return result, plan
