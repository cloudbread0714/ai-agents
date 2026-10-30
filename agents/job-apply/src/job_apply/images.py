"""Saving a posting's body images for the session to read (research R8).

Boards often post the whole body as one tall picture. Pieces at most ``PIECE_HEIGHT``
pixels tall stay legible when the session opens them.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

PIECE_HEIGHT = 1300


def _pieces(data: bytes) -> list[pymupdf.Pixmap]:
    src = pymupdf.Pixmap(data)
    if src.alpha:
        src = pymupdf.Pixmap(src, 0)
    if src.colorspace is None or src.colorspace.n != 3:
        src = pymupdf.Pixmap(pymupdf.csRGB, src)
    out = []
    for top in range(0, src.height, PIECE_HEIGHT):
        rect = pymupdf.IRect(0, top, src.width, min(src.height, top + PIECE_HEIGHT))
        piece = pymupdf.Pixmap(src.colorspace, rect, False)
        piece.copy(src, rect)
        piece.set_origin(0, 0)
        out.append(piece)
    return out


def save(blobs: list[bytes], dest: Path) -> list[Path]:
    """Write ``NN-k.png`` pieces in page order, replacing earlier ones; unreadable blobs
    are skipped."""
    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob("*.png"):
        old.unlink()
    saved: list[Path] = []
    for n, data in enumerate(blobs, 1):
        try:
            pieces = _pieces(data)
        except (RuntimeError, ValueError):
            continue
        for k, piece in enumerate(pieces, 1):
            path = dest / f"{n:02d}-{k}.png"
            piece.save(path)
            saved.append(path)
    return saved
