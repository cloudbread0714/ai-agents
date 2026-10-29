"""Posting record (data/posted.json v2): one plan item per KST date, one summary per week."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from shared.files import write_text_atomic
from troubleshoot_lab.models import DailyPost, Posted

RETENTION = timedelta(days=365)


class PostedFormatError(Exception):
    pass


def load(path: Path) -> Posted:
    if not path.exists():
        return Posted()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") == 1:
        if data.get("daily") or data.get("weekly"):
            raise PostedFormatError("posted.json v1 with records cannot be upgraded")
        return Posted()
    return Posted.model_validate(data)


def save(path: Path, posted: Posted, *, now: datetime) -> None:
    """Drop records older than a year (never the open problem), then write atomically."""
    cutoff = now - RETENTION
    kept = Posted(
        daily=[d for d in posted.daily if d.posted_at >= cutoff or d.outcome == "open"],
        weekly=[w for w in posted.weekly if w.posted_at >= cutoff],
    )
    write_text_atomic(path, kept.model_dump_json(indent=2, exclude_none=False) + "\n")


def posted_on(posted: Posted, day: date) -> DailyPost | None:
    return next((d for d in posted.daily if d.date_kst == day), None)


def open_post(posted: Posted) -> DailyPost | None:
    """The problem waiting for ✅ (at most one)."""
    return next((d for d in posted.daily if d.outcome == "open"), None)


def weekly_posted(posted: Posted, week_start: date) -> bool:
    return any(w.week_start_kst == week_start for w in posted.weekly)


def before(posted: Posted, day: date) -> list[DailyPost]:
    return sorted((d for d in posted.daily if d.date_kst < day), key=lambda d: d.date_kst)


def previous_daily(posted: Posted, day: date) -> DailyPost | None:
    earlier = before(posted, day)
    return earlier[-1] if earlier else None


def last_day(posted: Posted, day: date) -> int:
    """Highest plan day posted before ``day`` (0 when none)."""
    return max((d.day for d in before(posted, day) if d.kind == "day" and d.day), default=0)


def scenario_ids(post: DailyPost) -> list[str]:
    ids = [post.main_id] if post.main_kind == "scenario" else []
    return ids + ([post.second_id] if post.second_id else [])


def last_posted(posted: Posted, scenario_id: str, day: date | None = None) -> date | None:
    days = [
        d.date_kst
        for d in posted.daily
        if scenario_id in scenario_ids(d) and (day is None or d.date_kst < day)
    ]
    return max(days) if days else None


def posted_ids(posted: Posted) -> set[str]:
    return {sid for d in posted.daily for sid in scenario_ids(d)}


def posted_mains(posted: Posted) -> set[str]:
    return {d.main_id for d in posted.daily}
