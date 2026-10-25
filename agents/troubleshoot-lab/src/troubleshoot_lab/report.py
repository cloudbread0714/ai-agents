"""Incident report drafts and the ``--done`` check (contracts/report.md, research R23).

Only the header facts, the measurement table (measured values or explicit statuses) and the
interview questions are filled in. Symptom, cause, analysis, fix and prevention are the
learner's to write; nothing here writes them (FR-020).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from troubleshoot_lab.measure import cell
from troubleshoot_lab.models import FIELD_LABEL, Scenario
from troubleshoot_lab.progress import Attempt

KST = ZoneInfo("Asia/Seoul")
REPORTS_REL = Path("agents/troubleshoot-lab/docs/reports")
TEMPLATE_REL = Path("agents/troubleshoot-lab/templates/report.md")
REQUIRED = ("증상", "원인", "분석 과정", "해결 방법", "재발 방지")
INTERVIEW_HEADING = "면접 질문 답변"
PHASES = ("baseline", "fault", "after")
TABLE_ROWS = (
    ("평균 응답 시간 (ms)", ("avg_ms",)),
    ("p95 응답 시간 (ms)", ("p95_ms",)),
    ("처리량 (req/s)", ("rps",)),
    ("오류율 (%)", ("error_rate",)),
    ("CPU 평균 / 최대 (%)", ("cpu_avg_pct", "cpu_max_pct")),
    ("메모리 최대 (MiB)", ("mem_max_mib",)),
)
_COMMENT = re.compile(r"<!--.*?-->", re.S)

ReportStatus = Literal["none", "draft", "missing", "done"]


def report_rel_path(attempt: Attempt) -> Path:
    day = (attempt.ended or attempt.started).astimezone(KST).date()
    return REPORTS_REL / f"{day.isoformat()}-{attempt.scenario_id}-{attempt.attempt}.md"


def status(attempt: Attempt, repo_root: Path) -> ReportStatus:
    if attempt.end_type not in ("solved", "gave_up"):
        return "none"
    exists = (repo_root / report_rel_path(attempt)).exists()
    if attempt.reviewed and exists:
        return "done"
    return "draft" if exists else "missing"


def measurement_table(attempt: Attempt) -> str:
    lines = ["| 지표 | 정상 | 장애 | 해결 후 |", "|------|------|------|---------|"]
    for label, keys in TABLE_ROWS:
        cells = []
        for phase in PHASES:
            event = attempt.measurements.get(phase)
            if event is None:
                cells.append("측정하지 않음")
                continue
            values = [cell(event.metrics[k].model_dump(), k, event.skip_reason) for k in keys]
            cells.append(" / ".join(values))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render(attempt: Attempt, scenario: Scenario, template: str) -> str:
    questions = "\n\n".join(
        f"### Q{i}. {q}\n<!-- 직접 작성 -->" for i, q in enumerate(scenario.interview, 1)
    )
    values = {
        "title": scenario.title,
        "curriculum_no": scenario.curriculum_no,
        "field": FIELD_LABEL[scenario.field],
        "attempt": str(attempt.attempt),
        "result": "해결" if attempt.end_type == "solved" else "포기",
        "hints": str(attempt.hints),
        "table": measurement_table(attempt),
        "questions": questions,
    }
    out = template
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", value)
    return out


def create_draft(attempt: Attempt, scenario: Scenario, repo_root: Path) -> tuple[Path, bool]:
    """Write the draft unless it already exists. Returns (repo-relative path, created)."""
    rel = report_rel_path(attempt)
    path = repo_root / rel
    if path.exists():
        return rel, False
    template = (repo_root / TEMPLATE_REL).read_text(encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(attempt, scenario, template), encoding="utf-8")
    return rel, True


def _sections(text: str, level: str) -> dict[str, str]:
    pattern = re.compile(rf"^{level} (.+?)\s*$", re.M)
    matches = list(pattern.finditer(text))
    out = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[m.group(1)] = text[m.end() : end]
    return out


def _filled(body: str) -> bool:
    return bool(_COMMENT.sub("", body).strip())


def check_done(path: Path, scenario: Scenario) -> tuple[list[str], int]:
    """Return (missing or empty sections, number of answered interview questions)."""
    text = path.read_text(encoding="utf-8")
    sections = _sections(text, "##")
    missing = [name for name in REQUIRED if not _filled(sections.get(name, ""))]
    answers = _sections(sections.get(INTERVIEW_HEADING, ""), "###")
    answered = 0
    for i in range(1, len(scenario.interview) + 1):
        body = next((b for title, b in answers.items() if title.startswith(f"Q{i}.")), None)
        if body is not None and _filled(body):
            answered += 1
        else:
            missing.append(f"{INTERVIEW_HEADING} Q{i}")
    return missing, answered
