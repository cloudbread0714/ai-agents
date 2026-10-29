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


def issue_text(issue) -> str:
    where = f"슬라이드 {issue.slide}" + (
        f" shape {issue.shape_id}" if issue.shape_id is not None else ""
    )
    return f"{where}: {KIND_LABEL[issue.kind]} ({issue.detail})"


def render(
    meta: Meta,
    plan: TailorPlan | None,
    base_dump: dict[str, Any] | None,
    warnings: dict[str, list[dict[str, Any]]] | None,
    max_attempts: int,
) -> str:
    out = ["# 변경 내역", "", "## 사용한 원본", ""]
    out += _table(
        ["파일", "해시(앞 12자)", "수정 시각"],
        [
            [name, info.sha256[:12], info.mtime.isoformat(timespec="seconds")]
            for name, info in (
                ("resume.pdf", meta.sources.resume),
                ("portfolio.pptx", meta.sources.portfolio),
            )
        ],
    )
    out += ["", "## 이력서 변경", ""]
    out += _table(
        ["섹션", "전", "후", "근거", "이유"],
        [
            [c.section, c.before, c.after, c.source, c.reason]
            for c in (plan.resume.changes if plan else [])
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
        if e.text is not None:
            after = e.text
        elif e.runs is not None:
            after = "".join(e.runs)
        elif e.op and e.op.kind == "insert_after":
            after = f"(뒤에 추가) {e.op.text}"
        else:
            after = "(삭제)"
        rows.append(
            [
                f"{e.slide} / shape {e.shape_id} / 문단 {e.paragraph}",
                before,
                after,
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
    dump_path = folder / "base" / "portfolio.json"
    base_dump = json.loads(dump_path.read_text(encoding="utf-8")) if dump_path.is_file() else None
    (folder / "changes.md").write_text(
        render(meta, plan, base_dump, warnings, max_attempts), encoding="utf-8"
    )
