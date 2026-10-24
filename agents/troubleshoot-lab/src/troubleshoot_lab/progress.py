"""Append-only learning event log (v2) and the six-step state derived from it (research R22)."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from shared.files import write_text_atomic
from troubleshoot_lab.models import Event, Progress

ScenarioStatus = Literal["new", "pending", "solved", "gave_up"]
Stage = Literal["started", "baseline_ok", "injected", "fault_ok", "solved", "gave_up", "reset"]
_ENDS = {"scenario_solved": "solved", "scenario_gave_up": "gave_up", "scenario_reset": "reset"}


class ProgressFormatError(Exception):
    pass


class ProgressStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Progress:
        if not self.path.exists():
            return Progress()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("version") == 1:
            if data.get("events"):
                raise ProgressFormatError("progress.json v1 with events cannot be upgraded")
            return Progress()
        return Progress.model_validate(data)

    def append(self, event: Event) -> Progress:
        progress = self.load()
        # stable sort keeps same-timestamp events in the order they were written
        events = sorted([*progress.events, event], key=lambda e: e.ts)
        updated = Progress(events=events)
        write_text_atomic(self.path, updated.model_dump_json(indent=2, exclude_none=True) + "\n")
        return updated


@dataclass
class Attempt:
    scenario_id: str
    attempt: int
    started: datetime
    stage: Stage = "started"
    measurements: dict[str, Event] = field(default_factory=dict)  # phase -> latest measured
    hints: int = 0
    end_type: str | None = None  # solved | gave_up | reset
    ended: datetime | None = None
    report: str | None = None
    answered: int = 0

    @property
    def active(self) -> bool:
        return self.end_type is None

    @property
    def reviewed(self) -> bool:
        return self.report is not None


def attempts(progress: Progress, scenario_id: str | None = None) -> list[Attempt]:
    by_key: dict[tuple[str, int], Attempt] = {}
    for e in progress.events:
        if e.attempt is None or (scenario_id is not None and e.id != scenario_id):
            continue
        key = (e.id, e.attempt)
        if e.type == "scenario_started":
            by_key[key] = Attempt(e.id, e.attempt, e.ts)
            continue
        a = by_key.get(key)
        if a is None:
            continue
        if e.type == "measured":
            a.measurements[e.phase] = e
            if e.phase == "baseline" and a.stage == "started":
                a.stage = "baseline_ok"
            elif e.phase == "fault" and a.stage == "injected":
                a.stage = "fault_ok"
        elif e.type == "fault_injected" and a.active:
            a.stage = "injected"
        elif e.type == "hint_opened":
            a.hints += 1
        elif e.type in _ENDS and a.active:
            a.end_type = _ENDS[e.type]
            a.stage = a.end_type
            a.ended = e.ts
        elif e.type == "report_completed":
            a.report, a.answered = e.report, e.answered or 0
    return sorted(by_key.values(), key=lambda a: (a.started, a.scenario_id))


def active_attempt(progress: Progress) -> Attempt | None:
    open_ = [a for a in attempts(progress) if a.active]
    return open_[-1] if open_ else None


def active_scenario(progress: Progress) -> str | None:
    a = active_attempt(progress)
    return a.scenario_id if a else None


def latest_attempt(progress: Progress, scenario_id: str) -> Attempt | None:
    found = attempts(progress, scenario_id)
    return found[-1] if found else None


def next_attempt_no(progress: Progress, scenario_id: str) -> int:
    found = attempts(progress, scenario_id)
    return max((a.attempt for a in found), default=0) + 1


def finished_attempts(progress: Progress) -> list[Attempt]:
    return [a for a in attempts(progress) if a.end_type in ("solved", "gave_up")]


def hints_in_active(progress: Progress, scenario_id: str) -> int:
    a = latest_attempt(progress, scenario_id)
    return a.hints if a and a.active else 0


def scenario_status(
    progress: Progress, scenario_id: str, posted_ids: Iterable[str] = ()
) -> ScenarioStatus:
    types = {e.type for e in progress.events if e.id == scenario_id}
    if "scenario_solved" in types:
        return "solved"
    if "scenario_gave_up" in types:
        return "gave_up"
    if "scenario_started" in types or scenario_id in set(posted_ids):
        return "pending"
    return "new"


def mission_done(progress: Progress, mission_id: str) -> bool:
    return any(e.type == "mission_completed" and e.id == mission_id for e in progress.events)


def done_missions(progress: Progress) -> set[str]:
    return {e.id for e in progress.events if e.type == "mission_completed"}


def last_event(progress: Progress, scenario_id: str, event_type: str) -> Event | None:
    found = [e for e in progress.events if e.id == scenario_id and e.type == event_type]
    return found[-1] if found else None


def first_event(progress: Progress, scenario_id: str, event_type: str) -> Event | None:
    return next((e for e in progress.events if e.id == scenario_id and e.type == event_type), None)


def events_between(progress: Progress, start: datetime, end: datetime) -> list[Event]:
    return [e for e in progress.events if start <= e.ts <= end]
