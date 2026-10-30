"""The resume original as a DOCX: its text structure (``resume.json``, ``resume.txt``) and
applying ``tailor.json`` resume edits to it (research R7).

Paragraphs are numbered 0.. in document order, entering tables, rows, cells and content
controls; ``resume.json`` records where each one sits (table/row/cell) and which
``resume.txt`` line holds its text. Only paragraph text and the row order inside a table
change. New text goes into the paragraph's first run, keeping its ``w:rPr``; inserted
paragraphs are clones of the paragraph they follow. The design guard (docx_guard.py)
checks the result before anything is written.
"""

from __future__ import annotations

import copy
import io
import json
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from lxml import etree

from job_apply.errors import PlanError
from job_apply.models import ResumeEdit, TailorPlan

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
DOCUMENT = "word/document.xml"
# Paragraph children that carry text; everything else (pPr, bookmarks, proofing marks) stays.
_RUN_LIKE = (f"{W}r", f"{W}hyperlink", f"{W}fldSimple", f"{W}smartTag", f"{W}ins", f"{W}del")
# Runs holding these are never removed by a text edit (the design guard would reject it).
_OBJECTS = (f"{W}drawing", f"{W}pict", f"{W}object")


def read_document(docx: Path | bytes) -> etree._Element:
    src = io.BytesIO(docx) if isinstance(docx, bytes) else docx
    with zipfile.ZipFile(src) as z:
        return etree.fromstring(z.read(DOCUMENT))


def _blocks(container: etree._Element) -> Iterator[etree._Element]:
    """Paragraphs and tables directly in ``container``, looking through content controls."""
    for el in container:
        if el.tag in (f"{W}p", f"{W}tbl"):
            yield el
        elif el.tag == f"{W}sdt":
            content = el.find(f"{W}sdtContent")
            if content is not None:
                yield from _blocks(content)


def rows(tbl: etree._Element) -> list[etree._Element]:
    return tbl.findall(f"{W}tr")


def walk(root: etree._Element) -> Iterator[tuple[etree._Element, dict[str, int | None]]]:
    """Yield (w:p, where) in document order; tables are numbered 1.. as they are met."""
    counter = [0]

    def visit(container, where):
        for el in _blocks(container):
            if el.tag == f"{W}p":
                yield el, where
                continue
            counter[0] += 1
            table = counter[0]
            for r, tr in enumerate(rows(el)):
                for c, tc in enumerate(tr.findall(f"{W}tc")):
                    yield from visit(tc, {"table": table, "row": r, "cell": c})

    yield from visit(root.find(f"{W}body"), {"table": None, "row": None, "cell": None})


def tables(root: etree._Element) -> list[etree._Element]:
    """Every table in the numbering :func:`walk` uses."""
    found: list[etree._Element] = []

    def visit(container):
        for el in _blocks(container):
            if el.tag == f"{W}tbl":
                found.append(el)
                for tr in rows(el):
                    for tc in tr.findall(f"{W}tc"):
                        visit(tc)

    visit(root.find(f"{W}body"))
    return found


def _run_text(r: etree._Element) -> str:
    out = []
    for el in r.iter(f"{W}t", f"{W}tab", f"{W}br", f"{W}cr"):
        out.append(el.text or "" if el.tag == f"{W}t" else "\t" if el.tag == f"{W}tab" else "\n")
    return "".join(out)


def _runs(p: etree._Element) -> list[etree._Element]:
    """Text runs of the paragraph in order, including those inside hyperlinks and fields."""
    return [r for r in p.iter(f"{W}r") if r.find(f"{W}t") is not None]


def paragraph_text(p: etree._Element) -> str:
    return "".join(_run_text(r) for r in p.iter(f"{W}r") if r.getparent().tag != f"{W}del")


def dump(root: etree._Element) -> dict[str, Any]:
    paragraphs, line = [], 0
    for i, (p, where) in enumerate(walk(root)):
        text = paragraph_text(p)
        entry: dict[str, Any] = {"paragraph": i, **where, "text": text}
        entry["runs"] = [_run_text(r) for r in _runs(p)]
        if text.strip():
            line += 1
            entry["line"] = line
        paragraphs.append(entry)
    return {
        "paragraph_count": len(paragraphs),
        "tables": [{"table": n, "rows": len(rows(t))} for n, t in enumerate(tables(root), 1)],
        "paragraphs": paragraphs,
    }


def dump_file(docx: Path, json_out: Path, txt_out: Path) -> dict[str, Any]:
    """``resume.json`` and ``resume.txt`` (one line per non-empty paragraph, so
    ``resume.txt:L<n>`` is the paragraph whose ``line`` is n)."""
    data = dump(read_document(docx))
    json_out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [" ".join(p["text"].split()) for p in data["paragraphs"] if "line" in p]
    txt_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return data


def all_text(data: dict[str, Any]) -> list[str]:
    return [p["text"] for p in data["paragraphs"] if p["text"]]


# --- applying edits ---------------------------------------------------------------------


def _top_child(p: etree._Element, el: etree._Element) -> etree._Element:
    while el.getparent() is not p:
        el = el.getparent()
    return el


def _fill(r: etree._Element, text: str) -> None:
    """Replace the run's content with ``text`` (line breaks as ``w:br``), keeping ``w:rPr``."""
    for el in list(r):
        if el.tag != f"{W}rPr":
            r.remove(el)
    for n, part in enumerate(text.split("\n")):
        if n:
            r.append(r.makeelement(f"{W}br", {}))
        t = r.makeelement(f"{W}t", {})
        t.text = part
        t.set(XML_SPACE, "preserve")
        r.append(t)


def _has_object(el: etree._Element) -> bool:
    return next(el.iter(*_OBJECTS), None) is not None


def _set_text(p: etree._Element, text: str) -> None:
    """Text into the first text run (its formatting kept); every other text run is removed.
    Runs with pictures or embedded objects stay where they are."""
    first = next(iter(_runs(p)), None)
    keep = _top_child(p, first) if first is not None else None
    for el in list(p):
        if el.tag in _RUN_LIKE and el is not keep and not _has_object(el):
            p.remove(el)
    if first is None:
        first = p.makeelement(f"{W}r", {})
        p.append(first)
    else:
        for r in list(keep.iter(f"{W}r")):
            if r is not first and not _has_object(r):
                r.getparent().remove(r)
    _fill(first, text)


def _set_runs(p: etree._Element, texts: list[str], where: str) -> None:
    runs = _runs(p)
    if len(runs) != len(texts):
        raise PlanError(f"{where}: runs는 원본 run 개수({len(runs)})와 같아야 해요")
    for r, text in zip(runs, texts, strict=True):
        _fill(r, text)


def _target(paragraphs: list[etree._Element], edit: ResumeEdit, where: str) -> etree._Element:
    if edit.paragraph >= len(paragraphs):
        raise PlanError(
            f"{where}: 문단 {edit.paragraph}이(가) 없어요 (이력서 문단 {len(paragraphs)}개)"
        )
    return paragraphs[edit.paragraph]


def _reorder(tbl: etree._Element, order: list[int], where: str) -> None:
    trs = rows(tbl)
    if sorted(order) != list(range(len(trs))):
        raise PlanError(f"{where}: order는 0..{len(trs) - 1}의 순열이어야 해요 (받은 값: {order})")
    anchor = trs[-1].getnext()
    parent = tbl
    for tr in trs:
        parent.remove(tr)
    for n in order:
        if anchor is not None:
            anchor.addprevious(trs[n])
        else:
            parent.append(trs[n])


def apply(base_docx: Path, plan: TailorPlan) -> bytes:
    root = read_document(base_docx)
    paragraphs = [p for p, _where in walk(root)]
    found_tables = tables(root)
    edits = plan.resume.edits
    resolved = [(e, _target(paragraphs, e, f"resume.edits[{i}]")) for i, e in enumerate(edits)]
    # Text first, then inserts (after the original paragraph, in plan order), deletes last,
    # so every edit addresses the base paragraph numbering.
    for i, (edit, p) in enumerate(resolved):
        if edit.text is not None:
            _set_text(p, edit.text)
        elif edit.runs is not None:
            _set_runs(p, edit.runs, f"resume.edits[{i}]")
    last_inserted: dict[int, etree._Element] = {}
    for edit, p in resolved:
        if edit.op and edit.op.kind == "insert_after":
            clone = copy.deepcopy(p)
            _set_text(clone, edit.op.text or "")
            last_inserted.get(id(p), p).addnext(clone)
            last_inserted[id(p)] = clone
    for i, (edit, p) in enumerate(resolved):
        if edit.op and edit.op.kind == "delete":
            parent = p.getparent()
            if len(parent.findall(f"{W}p")) <= 1:
                raise PlanError(f"resume.edits[{i}]: 칸의 마지막 문단은 지울 수 없어요")
            parent.remove(p)
    for i, ro in enumerate(plan.resume.row_order):
        where = f"resume.row_order[{i}]"
        if not 1 <= ro.table <= len(found_tables):
            raise PlanError(f"{where}: 표 {ro.table}이(가) 없어요 (표 {len(found_tables)}개)")
        _reorder(found_tables[ro.table - 1], ro.order, where)

    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    out = io.BytesIO()
    with zipfile.ZipFile(base_docx) as src, zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            dst.writestr(item, data if item.filename == DOCUMENT else src.read(item.filename))
    return out.getvalue()
