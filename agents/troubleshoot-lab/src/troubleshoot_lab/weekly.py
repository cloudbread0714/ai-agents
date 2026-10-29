"""Weekly learning summary (data-model.md 주간 요약, FR-038–FR-039)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from troubleshoot_lab import posted as posted_mod
from troubleshoot_lab import progress as prog
from troubleshoot_lab import report as rep
from troubleshoot_lab.catalog import Catalog
from troubleshoot_lab.gate import days_open
from troubleshoot_lab.models import FIELDS, Posted, Progress
from troubleshoot_lab.planner import plan_today

KST = ZoneInfo("Asia/Seoul")
PENDING_SHOWN = 5


@dataclass
class WeeklySummary:
    week_start: date
    until: datetime
    progress_label: str = ""
    solved: int = 0
    gave_up: int = 0
    hints: int = 0
    reviewed: int = 0
    answered: int = 0
    pending: list[tuple[str, int]] = field(default_factory=list)  # (title, attempt)
    weak_field: str | None = None
    solved_posts: int = 0  # daily problems closed by ✅ this week (004)
    stalled_days: int = 0  # days that got a reminder instead of a new problem
    open_post: tuple[str, int] | None = None  # (title, days since posted)
    next_topic: str | None = None
    empty: bool = True


def week_start(now: datetime) -> date:
    today = now.astimezone(KST).date()
    return today - timedelta(days=today.weekday())


def progress_label(catalog: Catalog, posted: Posted, today: date) -> str:
    mains = posted_mod.posted_mains(posted)
    plan = catalog.plan
    if plan is not None:
        extras_done = sum(1 for e in plan.extras if e in mains)
        last = posted_mod.last_day(posted, today + timedelta(days=1))
        if last >= 21 and extras_done:
            return (
                f"심화 {extras_done}/{len(plan.extras)}"
                if extras_done < len(plan.extras)
                else "복습 단계"
            )
        return f"{last}/21일 차"
    return "계획 없음"


def summarize(
    catalog: Catalog, progress: Progress, posted: Posted, now: datetime, repo_root: Path
) -> WeeklySummary:
    start_day = week_start(now)
    start = datetime.combine(start_day, time(0), KST)
    today = now.astimezone(KST).date()
    events = prog.events_between(progress, start, now)
    counts = Counter(e.type for e in events)
    s = WeeklySummary(week_start=start_day, until=now)
    s.progress_label = progress_label(catalog, posted, today)
    s.solved = counts["scenario_solved"]
    s.gave_up = counts["scenario_gave_up"]
    s.hints = counts["hint_opened"]
    s.reviewed = counts["report_completed"]
    s.answered = sum(e.answered or 0 for e in events if e.type == "report_completed")
    s.empty = not events
    pending = [a for a in prog.finished_attempts(progress) if rep.status(a, repo_root) != "done"]
    s.pending = [(_title(catalog, a.scenario_id), a.attempt) for a in pending[:PENDING_SHOWN]]
    s.weak_field = _weak_field(catalog, progress, start, now)
    s.solved_posts = sum(1 for d in posted.daily if d.resolved_at and start <= d.resolved_at <= now)
    s.stalled_days = sum(1 for d in posted.daily for r in d.reminders if start_day <= r <= today)
    if (current := posted_mod.open_post(posted)) is not None:
        s.open_post = (_title(catalog, current.main_id), days_open(current, today))
    nxt = plan_today(catalog, progress, posted, today + timedelta(days=1))
    if nxt is not None:
        s.next_topic = nxt.plan_day.topic if nxt.plan_day else _title(catalog, nxt.main_id)
    return s


def _weak_field(catalog: Catalog, progress: Progress, start: datetime, now: datetime) -> str | None:
    """Max of hints + 2 × (gave up + reset without solving) over finished attempts started
    this week, by primary field. Ties: fewer solves, then ①→⑥. All zero → None."""
    score: Counter[str] = Counter()
    solves: Counter[str] = Counter()
    seen: set[str] = set()
    for a in prog.attempts(progress):
        scenario = catalog.scenarios.get(a.scenario_id)
        if scenario is None or a.end_type is None or not (start <= a.started <= now):
            continue
        f = scenario.field
        seen.add(f)
        score[f] += a.hints + (2 if a.end_type in ("gave_up", "reset") else 0)
        solves[f] += a.end_type == "solved"
    if not seen or max(score[f] for f in seen) == 0:
        return None
    return min(seen, key=lambda f: (-score[f], solves[f], FIELDS.index(f)))


def _title(catalog: Catalog, item_id: str) -> str:
    item = catalog.get(item_id)
    return item.title if item else item_id
