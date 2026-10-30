"""``changes.md``, generated from tailor.json and the apply/verify results (data-model §7).
The session never writes it by hand."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from job_apply.models import Meta, TailorPlan

KIND_LABEL = {
    "overflow": "글자 넘침",
    "offslide": "슬라이드 밖",
    "overlap": "겹침",
    "visual": "눈으로 확인",
}


def cell(text: str | None) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r", "")
        .replace("\n", "<br>")
    )


def _table(header: list[str], rows: list[list[str | None]]) -> list[str]:
    if not rows:
        return ["(없음)"]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return lines


def _paragraph(dump: dict[str, Any], slide: int, shape_id: int, paragraph: int) -> str | None:
    for s in dump["slides"]:
        if s["slide"] != slide:
            continue
        for sh in s["shapes"]:
            if sh["shape_id"] == shape_id:
                ps = sh.get("paragraphs", [])
                return ps[paragraph]["text"] if paragraph < len(ps) else None
    return None


def issue_place(issue) -> str:
    if issue.file == "resume":
        return f"이력서 {issue.slide}쪽"
    return f"슬라이드 {issue.slide}" + (
        f" shape {issue.shape_id}" if issue.shape_id is not None else ""
    )


def issue_text(issue) -> str:
    return f"{issue_place(issue)}: {KIND_LABEL[issue.kind]} ({issue.detail})"


def _where(p: dict[str, Any] | None) -> str:
    if p is None or p.get("table") is None:
        return "본문"
    return f"표 {p['table']} / 행 {p['row']} / 칸 {p['cell']}"


def _after(e) -> str:
    if e.text is not None:
        return e.text
    if e.runs is not None:
        return "".join(e.runs)
    if e.op and e.op.kind == "insert_after":
        return f"(뒤에 추가) {e.op.text}"
    return "(삭제)"


def render(
    meta: Meta,
    plan: TailorPlan | None,
    base_dump: dict[str, Any] | None,
    resume_dump: dict[str, Any] | None,
    warnings: dict[str, list[dict[str, Any]]] | None,
    max_attempts: int,
) -> str:
    out = ["# 변경 내역", "", "## 사용한 원본", ""]
    out += _table(
        ["파일", "해시(앞 12자)", "수정 시각"],
        [
            [name, info.sha256[:12], info.mtime.isoformat(timespec="seconds")]
            for name, info in (
                ("resume.docx", meta.sources.resume),
                ("portfolio.pptx", meta.sources.portfolio),
            )
        ],
    )
    out += ["", "## 이력서 문구 변경", ""]
    paragraphs = resume_dump["paragraphs"] if resume_dump else []
    rows = []
    for e in plan.resume.edits if plan else []:
        p = paragraphs[e.paragraph] if e.paragraph < len(paragraphs) else None
        before = p["text"] if p else None
        rows.append([f"{e.paragraph} ({_where(p)})", before, _after(e), e.source, e.reason])
    out += _table(["문단", "전", "후", "근거", "이유"], rows)
    out += ["", "## 이력서 표 행 순서", ""]
    out += _table(
        ["표", "행 순서(원본 기준)", "이유"],
        [
            [str(r.table), ", ".join(map(str, r.order)), r.reason]
            for r in (plan.resume.row_order if plan else [])
        ],
    )
    out += ["", "## 포트폴리오 슬라이드 순서", ""]
    if plan:
        out += _table(
            ["결과", "원본"],
            [[str(i), str(n)] for i, n in enumerate(plan.portfolio.slide_order, 1)],
        )
        if plan.portfolio.order_reason:
            out += ["", f"이유: {plan.portfolio.order_reason}"]
    else:
        out.append("(없음)")
    out += ["", "## 포트폴리오 문구 변경", ""]
    rows = []
    for e in plan.portfolio.edits if plan else []:
        before = _paragraph(base_dump, e.slide, e.shape_id, e.paragraph) if base_dump else None
        rows.append(
            [
                f"{e.slide} / shape {e.shape_id} / 문단 {e.paragraph}",
                before,
                _after(e),
                e.source,
                e.reason,
            ]
        )
    out += _table(["슬라이드", "전", "후", "근거", "이유"], rows)
    out += ["", "## 렌더링 점검", "", f"시도 {meta.render.attempts}/{max_attempts}"]
    issues = meta.render.remaining_issues
    out += [f"- {issue_text(i)}" for i in issues] if issues else ["남은 문제 없음"]
    out += ["", "## 근거 검사 경고", ""]
    if warnings is None:
        out.append("(verify 전)")
    else:
        unresolved, acknowledged = warnings.get("unresolved", []), warnings.get("acknowledged", [])
        if not unresolved and not acknowledged:
            out.append("경고 없음")
        out += [f"- ⚠️ 해명 안 됨: {w['file']} `{w['token']}` ({w['kind']})" for w in unresolved]
        out += [
            f"- 해명됨: {w['file']} `{w['token']}` → {w['source']} ({w['reason']})"
            for w in acknowledged
        ]
    return "\n".join(out) + "\n"


def write(folder: Path, meta: Meta, plan: TailorPlan | None, warnings, max_attempts: int) -> None:
    def load(name: str) -> dict[str, Any] | None:
        path = folder / "base" / name
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    (folder / "changes.md").write_text(
        render(meta, plan, load("portfolio.json"), load("resume.json"), warnings, max_attempts),
        encoding="utf-8",
    )
