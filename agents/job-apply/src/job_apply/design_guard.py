"""Design preservation check run by every ``job apply`` before writing (research R3, FR-013).

1. Same parts; slides only reordered (``p:sldIdLst``).
2. Each slide equals its base slide once shape paragraphs are removed: shapes, positions,
   sizes, fills, pictures, layout references.
3. Every paragraph/run format in a changed shape is one the same base shape already had.
4. Theme, master, layout and media parts are unchanged.
XML parts compare in canonical form (python-pptx re-serializes them); binaries byte by byte.
Saving through python-pptx also drops zip directory entries, may reorder relationships and
rewrites ``[Content_Types].xml``, so those compare by meaning: relationships as a set, content
types as the type each part resolves to.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from lxml import etree

from job_apply.errors import DesignViolation

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
SLIDE_RE = re.compile(r"^ppt/slides/slide\d+\.xml$")
SKIP = ("docProps/",)
FORMAT_TAGS = (f"{A}pPr", f"{A}rPr", f"{A}endParaRPr")
_PARSER = etree.XMLParser(remove_blank_text=True)


def _parse(blob: bytes) -> etree._Element:
    return etree.fromstring(blob, _PARSER)


def _c14n(el: etree._Element) -> bytes:
    return etree.tostring(el, method="c14n")


def _is_xml(name: str) -> bool:
    return name.endswith((".xml", ".rels"))


def _strip_paragraphs(root: etree._Element) -> etree._Element:
    for body in root.iter(f"{P}txBody"):
        for p in body.findall(f"{A}p"):
            body.remove(p)
    return root


def _formats(sp: etree._Element) -> dict[str, set[bytes]]:
    found: dict[str, set[bytes]] = {tag: set() for tag in FORMAT_TAGS}
    body = sp.find(f"{P}txBody")
    if body is not None:
        for p in body.findall(f"{A}p"):
            for el in p.iter(*FORMAT_TAGS):
                found[el.tag].add(_c14n(el))
    return found


def _shapes(root: etree._Element) -> dict[str, etree._Element]:
    out = {}
    for sp in root.iter(f"{P}sp"):
        c_nv_pr = sp.find(f"{P}nvSpPr/{P}cNvPr")
        if c_nv_pr is not None:
            out[c_nv_pr.get("id")] = sp
    return out


def _check_slide(name: str, base: bytes, result: bytes, problems: list[str]) -> None:
    base_root, result_root = _parse(base), _parse(result)
    base_shapes, result_shapes = _shapes(base_root), _shapes(result_root)
    for sid, sp in result_shapes.items():
        allowed = _formats(base_shapes[sid]) if sid in base_shapes else {}
        for tag, formats in _formats(sp).items():
            extra = formats - allowed.get(tag, set())
            if extra:
                problems.append(
                    f"{name} shape {sid}: 원본에 없는 서식({etree.QName(tag).localname})"
                )
    if _c14n(_strip_paragraphs(base_root)) != _c14n(_strip_paragraphs(result_root)):
        problems.append(f"{name}: 도형·위치·크기·채우기·이미지 등 텍스트 외 변경")


def _sorted_slide_ids(blob: bytes) -> bytes:
    root = _parse(blob)
    lst = root.find(f"{P}sldIdLst")
    if lst is not None:
        items = sorted(lst, key=lambda el: el.get(R_ID) or "")
        for el in list(lst):
            lst.remove(el)
        for el in items:
            lst.append(el)
    return _c14n(root)


def _sorted_children(blob: bytes) -> list[bytes]:
    return sorted(_c14n(el) for el in _parse(blob))


CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"


def _part_types(blob: bytes, names: set[str]) -> dict[str, str | None]:
    root = _parse(blob)
    defaults = {
        (el.get("Extension") or "").lower(): el.get("ContentType")
        for el in root.iter(f"{CT}Default")
    }
    overrides = {el.get("PartName"): el.get("ContentType") for el in root.iter(f"{CT}Override")}
    return {
        n: overrides.get(f"/{n}", defaults.get(n.rsplit(".", 1)[-1].lower()))
        for n in names
        if n != "[Content_Types].xml"
    }


def _part_names(z: zipfile.ZipFile) -> set[str]:
    return {n for n in z.namelist() if not n.startswith(SKIP) and not n.endswith("/")}


def check(base_pptx: Path, result: bytes) -> None:
    problems: list[str] = []
    with zipfile.ZipFile(base_pptx) as zb, zipfile.ZipFile(io.BytesIO(result)) as zr:
        base_names = _part_names(zb)
        result_names = _part_names(zr)
        if base_names != result_names:
            added = sorted(result_names - base_names)
            removed = sorted(base_names - result_names)
            problems.append(f"파트가 달라짐 (추가 {added}, 삭제 {removed})")
        for name in sorted(base_names & result_names):
            b, r = zb.read(name), zr.read(name)
            if b == r:
                continue
            if SLIDE_RE.match(name):
                _check_slide(name, b, r, problems)
            elif name == "ppt/presentation.xml":
                if _sorted_slide_ids(b) != _sorted_slide_ids(r):
                    problems.append(f"{name}: 슬라이드 순서 외 변경")
            elif name == "[Content_Types].xml":
                if _part_types(b, base_names) != _part_types(r, base_names):
                    problems.append(f"{name}: 변경됨")
            elif name.endswith(".rels"):
                if _sorted_children(b) != _sorted_children(r):
                    problems.append(f"{name}: 변경됨")
            elif _is_xml(name):
                if _c14n(_parse(b)) != _c14n(_parse(r)):
                    problems.append(f"{name}: 변경됨")
            else:
                problems.append(f"{name}: 변경됨")
    if problems:
        raise DesignViolation("디자인 보존 위반:\n" + "\n".join(f"- {p}" for p in problems))
