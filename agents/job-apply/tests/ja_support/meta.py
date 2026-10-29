"""Minimal ``meta.json`` for folder tests."""

from __future__ import annotations

from pathlib import Path

from job_apply import folders
from job_apply.models import Meta


def make_meta(status="in_progress", posting_id="t-1", url_key="https://x.dev/1", fit=None) -> Meta:
    return Meta.model_validate(
        {
            "schema": 1,
            "status": status,
            "created_at": "2026-10-27T10:00:00+09:00",
            "fit_score": fit,
            "posting": {
                "id": posting_id,
                "origin": "direct",
                "url_key": url_key,
                "company": "가상테크",
                "role": "백엔드",
            },
            "sources": {
                "resume": {"sha256": "a" * 64, "mtime": "2026-10-27T00:00:00Z"},
                "portfolio": {"sha256": "b" * 64, "mtime": "2026-10-27T00:00:00Z"},
            },
        }
    )


def make_folder(applications: Path, name: str, **kw) -> Path:
    folder = applications / name
    folder.mkdir(parents=True)
    folders.write_meta(folder, make_meta(**kw))
    return folder
