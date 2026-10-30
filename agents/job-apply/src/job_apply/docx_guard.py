"""Design preservation check for the resume DOCX, run by every ``job apply`` before writing
(research R7, FR-013).

1. Same parts; every part except ``word/document.xml`` byte for byte.
2. ``word/document.xml`` equals the base once paragraphs are removed and each table's rows
   are sorted: tables, rows, cells, widths, borders, shading and section settings.
3. Pictures, embedded objects and section breaks are the same multiset as the base.
4. Every paragraph and run format (``w:pPr``, ``w:rPr``) is one the base already used.
"""

from __future__ import annotations

import io
import zipfile
from collections import Counter
from pathlib import Path

from lxml import etree

from job_apply.docx_doc import DOCUMENT, W
from job_apply.errors import DesignViolation

_PARSER = etree.XMLParser(remove_blank_text=True)
KEPT = (f"{W}drawing", f"{W}pict", f"{W}object", f"{W}sectPr")
FORMATS = (f"{W}pPr", f"{W}rPr")


def _c14n(el: etree._Element) -> bytes:
    return etree.tostring(el, method="c14n")


def _skeleton(root: etree._Element) -> bytes:
    for p in list(root.iter(f"{W}p")):
        p.getparent().remove(p)
    for tbl in root.iter(f"{W}tbl"):
        trs = tbl.findall(f"{W}tr")
        for tr in trs:
            tbl.remove(tr)
        for tr in sorted(trs, key=_c14n):
            tbl.append(tr)
    return _c14n(root)


def _multiset(root: etree._Element, tags) -> Counter[bytes]:
    return Counter(_c14n(el) for el in root.iter(*tags))


def _check_document(base: bytes, result: bytes, problems: list[str]) -> None:
    b, r = etree.fromstring(base, _PARSER), etree.fromstring(result, _PARSER)
    for tag in KEPT:
        if _multiset(b, [tag]) != _multiset(r, [tag]):
            problems.append(f"{DOCUMENT}: {etree.QName(tag).localname}(그림·개체·구역)가 달라짐")
    for tag in FORMATS:
        extra = set(_multiset(r, [tag])) - set(_multiset(b, [tag]))
        if extra:
            problems.append(f"{DOCUMENT}: 원본에 없는 서식({etree.QName(tag).localname})")
    if _skeleton(b) != _skeleton(r):
        problems.append(f"{DOCUMENT}: 표·칸·너비·테두리 등 텍스트 외 변경")


def check(base_docx: Path, result: bytes) -> None:
    problems: list[str] = []
    with zipfile.ZipFile(base_docx) as zb, zipfile.ZipFile(io.BytesIO(result)) as zr:
        base_names, result_names = set(zb.namelist()), set(zr.namelist())
        if base_names != result_names:
            added = sorted(result_names - base_names)
            removed = sorted(base_names - result_names)
            problems.append(f"파트가 달라짐 (추가 {added}, 삭제 {removed})")
        for name in sorted(base_names & result_names):
            b, r = zb.read(name), zr.read(name)
            if b == r:
                continue
            if name == DOCUMENT:
                _check_document(b, r, problems)
            else:
                problems.append(f"{name}: 변경됨")
    if problems:
        raise DesignViolation("이력서 디자인 보존 위반:\n" + "\n".join(f"- {p}" for p in problems))
