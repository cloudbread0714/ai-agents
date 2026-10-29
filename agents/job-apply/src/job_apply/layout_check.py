"""Overflow, off-slide and overlap detection on a rendered deck (research R6).

Characters from the PDF (PyMuPDF) are matched to the PPTX text shapes, first by content and
then by position; each shape's rendered text extent is compared with its box, the slide and
the other text shapes. Issues already present in the base rendering are dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from pptx import Presentation

from job_apply.models import RenderIssue
from job_apply.pptx_dump import dump

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub("", text)


@dataclass
class _Shape:
    shape_id: int
    box: tuple[float, float, float, float]
    text: str
    lines: list[tuple[float, float, float, float]] = field(default_factory=list)

    def extent(self) -> tuple[float, float, float, float] | None:
        if not self.lines:
            return None
        return (
            min(b[0] for b in self.lines),
            min(b[1] for b in self.lines),
            max(b[2] for b in self.lines),
            max(b[3] for b in self.lines),
        )


# Characters, not lines or words: MuPDF can merge text from two nearby shapes into one line
# or even one word. Text past the page edge is kept (no media-box clip) so it can be seen.
_FLAGS = pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_MEDIABOX_CLIP


def _pdf_chars(page) -> list[tuple[str, tuple[float, float, float, float]]]:
    chars = []
    for block in page.get_text("rawdict", flags=_FLAGS)["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                chars += [(ch["c"], tuple(ch["bbox"])) for ch in span["chars"] if ch["c"].strip()]
    return chars


def _geometry(s: _Shape, bbox) -> tuple[bool, bool, float]:
    x0, y0 = bbox[0], bbox[1]
    bx0, by0, bx1, by1 = s.box
    inside = bx0 - 2 <= x0 <= bx1 + 2 and by0 - 2 <= y0 <= by1 + 2
    below = bx0 - 2 <= x0 <= bx1 + 2 and y0 >= by0 - 2
    return (not inside, not below, abs(y0 - by0) + abs(x0 - bx0))


def _assign(shapes: list[_Shape], chars) -> None:
    """Follow each shape's text in order; a character goes to a shape that expects it next
    (position breaks ties), otherwise to the shape it sits in or under."""
    targets = {id(s): _norm(s.text) for s in shapes}
    pos = {id(s): 0 for s in shapes}
    for c, bbox in chars:
        expecting = [
            s
            for s in shapes
            if pos[id(s)] < len(targets[id(s)]) and targets[id(s)][pos[id(s)]] == c
        ]
        if expecting:
            owner = min(expecting, key=lambda s: (pos[id(s)] == 0, *_geometry(s, bbox)))
            pos[id(owner)] += 1
        else:
            owner = min(shapes, key=lambda s: _geometry(s, bbox), default=None)
            if owner is None or _geometry(owner, bbox)[1]:
                continue
        owner.lines.append(bbox)


def _excess(inner, outer) -> float:
    return max(outer[0] - inner[0], outer[1] - inner[1], inner[2] - outer[2], inner[3] - outer[3])


def find_issues(pptx: Path, pdf: Path, tolerance: float) -> list[RenderIssue]:
    data = dump(Presentation(str(pptx)))
    issues: list[RenderIssue] = []
    with pymupdf.open(pdf) as doc:
        for slide, page in zip(data["slides"], doc, strict=False):
            shapes = [
                _Shape(
                    sh["shape_id"],
                    tuple(sh["box_pt"]),
                    " ".join(p["text"] for p in sh["paragraphs"]),
                )
                for sh in slide["shapes"]
                if sh.get("paragraphs")
            ]
            _assign(shapes, _pdf_chars(page))
            rect = tuple(page.rect)
            n = slide["slide"]
            for s in shapes:
                ext = s.extent()
                if ext is None:
                    continue
                if (over := _excess(ext, s.box)) > tolerance:
                    issues.append(
                        RenderIssue(
                            slide=n, shape_id=s.shape_id, kind="overflow", detail=f"+{over:.0f}pt"
                        )
                    )
                if (off := _excess(ext, rect)) > tolerance:
                    issues.append(
                        RenderIssue(
                            slide=n, shape_id=s.shape_id, kind="offslide", detail=f"+{off:.0f}pt"
                        )
                    )
            for i, a in enumerate(shapes):
                for b in shapes[i + 1 :]:
                    ea, eb = a.extent(), b.extent()
                    if ea is None or eb is None:
                        continue
                    w = min(ea[2], eb[2]) - max(ea[0], eb[0])
                    h = min(ea[3], eb[3]) - max(ea[1], eb[1])
                    if w > tolerance and h > tolerance:
                        first, second = sorted((a.shape_id, b.shape_id))
                        issues.append(
                            RenderIssue(
                                slide=n,
                                shape_id=first,
                                kind="overlap",
                                detail=f"shape {second}와 겹침",
                            )
                        )
    return issues


def new_issues(
    result: list[RenderIssue], base: list[RenderIssue], slide_order: list[int]
) -> list[RenderIssue]:
    """Drop result issues whose base slide already had the same kind on the same shape."""
    known = {(i.slide, i.shape_id, i.kind) for i in base}
    return [i for i in result if (slide_order[i.slide - 1], i.shape_id, i.kind) not in known]
