"""Posted history persisted as JSON in the repo (contracts/history.schema.json, research R8)."""

from __future__ import annotations

import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from news_digest.models import Category, History, PostRecord

RETENTION = timedelta(days=365)


def load(path: Path) -> History:
    if not path.exists():
        return History()
    return History.model_validate_json(path.read_text(encoding="utf-8"))


def save(path: Path, history: History, *, now: datetime) -> None:
    """Prune entries older than a year, then write atomically (temp file + rename)."""
    kept = [p for p in history.posts if p.posted_at >= now - RETENTION]
    body = History(posts=kept).model_dump_json(indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def posted_ids(history: History) -> set[str]:
    return {p.article_id for p in history.posts}


def posted_today(history: History, today_kst: date) -> bool:
    return any(p.posted_date_kst == today_kst for p in history.posts)


def recent_categories(history: History, n: int) -> list[Category]:
    """Categories of the last ``n`` posts, oldest first."""
    return [p.category for p in history.posts[-n:]]


def append(history: History, record: PostRecord) -> History:
    posts = sorted([*history.posts, record], key=lambda p: p.posted_at)
    return History(posts=posts)
