"""Application folders: names, reuse, ``meta.json`` (data-model §4, research R12)."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from job_apply.models import Meta
from shared.files import write_text_atomic

PART_MAX = 40
_UNSAFE = re.compile(r'[/\\:*?"<>|\x00-\x1f\x7f]')


def clean(part: str) -> str:
    text = unicodedata.normalize("NFC", part)
    text = _UNSAFE.sub("", text).strip()
    text = re.sub(r"\s+", "-", text)
    return text[:PART_MAX] or "미상"


def base_name(day: date, company: str, role: str) -> str:
    return f"{day.isoformat()}_{clean(company)}_{clean(role)}"


def read_meta(folder: Path) -> Meta:
    return Meta.model_validate_json((folder / "meta.json").read_text(encoding="utf-8"))


def write_meta(folder: Path, meta: Meta) -> None:
    write_text_atomic(folder / "meta.json", meta.dump())


def iter_folders(applications: Path) -> Iterator[tuple[Path, Meta]]:
    if not applications.is_dir():
        return
    for folder in sorted(applications.iterdir()):
        if (folder / "meta.json").is_file():
            try:
                yield folder, read_meta(folder)
            except ValueError:
                continue


def find_resumable(applications: Path, posting_id: str, url_key: str) -> Path | None:
    """A failed or in-progress folder for the same posting (FR-019). Done folders never."""
    for folder, meta in iter_folders(applications):
        same = meta.posting.id == posting_id or meta.posting.url_key == url_key
        if same and meta.status in ("failed", "in_progress"):
            return folder
    return None


def new_folder(applications: Path, day: date, company: str, role: str) -> Path:
    name = base_name(day, company, role)
    folder, n = applications / name, 1
    while folder.exists():
        n += 1
        folder = applications / f"{name}_{n}"
    folder.mkdir(parents=True)
    return folder
