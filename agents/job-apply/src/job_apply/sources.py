"""Originals in ``private/``: read-only access, hashes, base copies (FR-007–FR-009).

The CLI never writes under ``private/``. Every command runs inside :func:`guard`, which
compares the originals' hashes at start and end; after ``init`` only ``base/`` copies are used.
"""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pptx import Presentation

from job_apply import docx_doc
from job_apply.config import Paths
from job_apply.errors import SourceChangedError, SourceError
from job_apply.models import SourceInfo, Sources


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def info(path: Path) -> SourceInfo:
    return SourceInfo(sha256=sha256(path), mtime=datetime.fromtimestamp(path.stat().st_mtime, UTC))


def check(paths: Paths) -> None:
    """Both originals exist and open. Raises SourceError naming the file (exit 5)."""
    for path in (paths.resume, paths.portfolio):
        if not path.is_file():
            raise SourceError(f"원본이 없어요: {paths.rel(path)}")
    try:
        docx_doc.read_document(paths.resume)
    except Exception as exc:  # noqa: BLE001 - any parse failure means "cannot read"
        raise SourceError(f"원본을 열 수 없어요: {paths.rel(paths.resume)} ({exc})") from None
    try:
        Presentation(str(paths.portfolio))
    except Exception as exc:  # noqa: BLE001
        raise SourceError(f"원본을 열 수 없어요: {paths.rel(paths.portfolio)} ({exc})") from None


def current(paths: Paths) -> Sources:
    return Sources(resume=info(paths.resume), portfolio=info(paths.portfolio))


def of_copies(paths: Paths, base: Path) -> Sources:
    """Hashes of the base copies (what this folder actually uses), mtimes of the originals."""

    def one(copy: Path, original: Path) -> SourceInfo:
        mtime = datetime.fromtimestamp(original.stat().st_mtime, UTC)
        return SourceInfo(sha256=sha256(copy), mtime=mtime)

    return Sources(
        resume=one(base / "resume.docx", paths.resume),
        portfolio=one(base / "portfolio.pptx", paths.portfolio),
    )


def _snapshot(paths: Paths) -> dict[str, str | None]:
    return {p.name: sha256(p) if p.is_file() else None for p in (paths.resume, paths.portfolio)}


@contextmanager
def guard(paths: Paths) -> Iterator[None]:
    """Raise SourceChangedError (exit 8) if an original changed while the command ran."""
    before = _snapshot(paths)
    yield
    after = _snapshot(paths)
    changed = [name for name in before if before[name] != after[name]]
    if changed:
        raise SourceChangedError(changed)


def copy_to_base(paths: Paths, base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(paths.resume, base / "resume.docx")
    shutil.copyfile(paths.portfolio, base / "portfolio.pptx")
