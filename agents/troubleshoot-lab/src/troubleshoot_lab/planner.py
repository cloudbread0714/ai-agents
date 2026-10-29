"""Today's plan item from the 21-day curriculum (data-model.md 일차 선택, FR-030).

Deterministic: the same catalog, plan, progress, posting record and date always give the
same pick. No LLM is involved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from troubleshoot_lab import posted as posted_mod
from troubleshoot_lab import progress as prog
from troubleshoot_lab.catalog import Catalog
from troubleshoot_lab.models import PlanDay, Posted, Progress

# "catchup" only appears in records from before solve-gated posting (004).
PickKind = Literal["day", "extra", "review"]


@dataclass(frozen=True)
class DayPick:
    kind: PickKind
    main_id: str
    main_kind: Literal["scenario", "mission"]
    day: int | None = None
    plan_day: PlanDay | None = None
    second_id: str | None = None
    review_flag: bool = False
    minutes: int = 0
    extra_index: int | None = None
    composite: bool = False


def _no_key(no: str) -> tuple[int, str]:
    m = re.match(r"\d+", no)
    return (int(m.group(0)) if m else 1000, no)


def _max_hints(progress: Progress, sid: str) -> int:
    return max((a.hints for a in prog.attempts(progress, sid)), default=0)


def _avoid(prev: str | None, candidates: list[str]) -> list[str]:
    """Drop yesterday's main item unless it is the only candidate (FR-030 rule 4)."""
    others = [c for c in candidates if c != prev]
    return others or candidates


def choose_from_pool(
    catalog: Catalog,
    progress: Progress,
    posted: Posted,
    pool: list[str],
    today: date,
    prev: str | None,
) -> str:
    """Composite day (FR-030 rule 5): unsolved never-posted → unsolved oldest-posted →
    gave up → most hints (gave up counts 3) → curriculum number."""
    published = posted_mod.posted_ids(posted)

    def key(sid: str):
        status = prog.scenario_status(progress, sid)
        if status not in ("solved", "gave_up"):
            rank = 0 if sid not in published else 1
        else:
            rank = 2 if status == "gave_up" else 3
        last = posted_mod.last_posted(posted, sid, today) if rank == 1 else None
        hints = 3 if status == "gave_up" else _max_hints(progress, sid)
        return (rank, last or date.min, -hints, _no_key(catalog.scenarios[sid].curriculum_no))

    return min(_avoid(prev, list(pool)), key=key)


def _review(catalog: Catalog, progress: Progress, prev: str | None) -> str | None:
    def ts(sid: str, event_type: str):
        e = prog.last_event(progress, sid, event_type)
        return e.ts if e else None

    gave_up = sorted(
        (s for s in catalog.scenarios if prog.scenario_status(progress, s) == "gave_up"),
        key=lambda s: (ts(s, "scenario_gave_up"), s),
    )
    solved = sorted(
        (s for s in catalog.scenarios if prog.scenario_status(progress, s) == "solved"),
        key=lambda s: (
            -_max_hints(progress, s),
            prog.first_event(progress, s, "scenario_solved").ts,
            s,
        ),
    )
    candidates = _avoid(prev, gave_up + solved)
    return candidates[0] if candidates else None


def plan_today(catalog: Catalog, progress: Progress, posted: Posted, today: date) -> DayPick | None:
    plan = catalog.plan
    if plan is None:
        return None
    previous = posted_mod.previous_daily(posted, today)
    prev_main = previous.main_id if previous else None
    second = plan_day = day = extra_index = None
    composite = False

    # A new item is only posted once the previous one is solved, so the plan day advances
    # per solved problem, not per calendar day (004 FR-004).
    next_day = posted_mod.last_day(posted, today) + 1
    if next_day <= 21:
        kind: PickKind = "day"
        day = next_day
        plan_day = plan.get(next_day)
        if plan_day.pool is not None:
            composite = True
            main = choose_from_pool(catalog, progress, posted, plan_day.pool, today, prev_main)
        else:
            main = plan_day.items[0]
            second = plan_day.items[1] if len(plan_day.items) > 1 else None
    else:
        mains = posted_mod.posted_mains(posted)
        remaining = [e for e in plan.extras if e not in mains]
        if remaining:
            kind, main = "extra", remaining[0]
            extra_index = plan.extras.index(main) + 1
        else:
            kind = "review"
            main = _review(catalog, progress, prev_main)
            if main is None:
                return None

    is_scenario = main in catalog.scenarios
    review_flag = is_scenario and kind == "day" and prog.scenario_status(progress, main) == "solved"
    return DayPick(
        kind=kind,
        main_id=main,
        main_kind="scenario" if is_scenario else "mission",
        day=day,
        plan_day=plan_day,
        second_id=second,
        review_flag=review_flag,
        minutes=catalog.minutes_with_warmups(main, prog.done_missions(progress)),
        extra_index=extra_index,
        composite=composite,
    )
