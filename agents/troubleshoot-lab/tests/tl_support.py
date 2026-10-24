"""Importable test helpers: temp catalogs with sentinel text, a plan writer, fake runners."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from troubleshoot_lab.models import METRIC_KEYS, Event, Progress

NOW = datetime(2026, 10, 26, 0, 0, tzinfo=UTC)  # Monday 09:00 KST
LAB_HOOK = "https://hooks.slack.com/services/T0/B0/LABLABLAB"
TEST_HOOK = "https://hooks.slack.com/services/T0/B0/TESTTESTTEST"


def hint_sentinel(scenario_id: str, n: int) -> str:
    return f"HINT-SENTINEL-{scenario_id}-{n}"


def solution_sentinel(scenario_id: str) -> str:
    return f"SOLUTION-SENTINEL-{scenario_id}"


def tag_sentinel(scenario_id: str) -> str:
    return f"TAG-SENTINEL-{scenario_id}"


def start_hint_sentinel(scenario_id: str) -> str:
    return f"STARTHINT-SENTINEL-{scenario_id}"


def interview_sentinel(scenario_id: str) -> str:
    return f"INTERVIEW-SENTINEL-{scenario_id}?"


def _script(path: Path, body: str = "exit 0") -> None:
    path.write_text(f"#!/usr/bin/env bash\n{body}\n")
    path.chmod(0o755)


def mission_spec(
    mission_id: str, *, steps=None, title=None, kind="warmup", minutes=None, env="compose"
):
    return {
        "id": mission_id,
        "env": env,
        "kind": kind,
        "title": title or f"미션 {mission_id}",
        "minutes": minutes if minutes is not None else (60 if kind == "concept" else 15),
        "goals": ["목표"],
        "steps": steps
        or [
            {"id": "first", "guide": "먼저 보기", "command": "echo one", "check": "state"},
            {
                "id": "second",
                "guide": "값 찾기",
                "command": "echo two",
                "check": "answer",
                "prompt": "토큰을 입력",
            },
        ],
    }


_numbers = iter(range(1, 10_000))


def scenario_spec(
    scenario_id: str,
    *,
    difficulty="beginner",
    warmups=("m-one",),
    title=None,
    fields=("linux",),
    env="compose",
    minutes=45,
    no=None,
    interview=None,
):
    return {
        "id": scenario_id,
        "curriculum_no": no or f"extra-{next(_numbers)}",
        "fields": list(fields),
        "env": env,
        "title": title or f"시나리오 {scenario_id}",
        "difficulty": difficulty,
        "minutes": minutes,
        "symptom": f"증상 {scenario_id}",
        "tags": [tag_sentinel(scenario_id)],
        "warmups": list(warmups),
        "start_hint": start_hint_sentinel(scenario_id),
        "measure": {"path": "/api/items", "service": "api", "duration_s": 5, "vus": 2},
        "interview": interview or [interview_sentinel(scenario_id)],
    }


def write_mission(root: Path, field_dir: str, spec: dict, *, scripts=True, dirname=None) -> Path:
    d = root / "missions" / field_dir / (dirname or spec["id"])
    d.mkdir(parents=True, exist_ok=True)
    (d / "mission.yaml").write_text(yaml.safe_dump(spec, allow_unicode=True))
    if scripts:
        _script(d / "setup.sh")
        _script(d / "verify.sh")
    return d


def write_scenario(
    root: Path, spec: dict, *, field_dir=None, hints=None, solution=None, scripts=True
) -> Path:
    d = root / "scenarios" / (field_dir or spec.get("fields", ["linux"])[0]) / spec["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "scenario.yaml").write_text(yaml.safe_dump(spec, allow_unicode=True))
    sid = spec["id"]
    (d / "hints.md").write_text(
        hints
        if hints is not None
        else "\n\n".join(f"## 힌트 {n}\n{hint_sentinel(sid, n)}" for n in (1, 2, 3)) + "\n"
    )
    (d / "solution.md").write_text(
        solution if solution is not None else f"## 원인\n{solution_sentinel(sid)}\n"
    )
    if scripts:
        for name in ("inject.sh", "verify.sh", "reset.sh"):
            _script(d / name)
    return d


def write_plan(root: Path, days: dict[int, dict] | None = None, *, extras=(), fill=None) -> None:
    """Write curriculum/plan.yaml. ``days`` overrides specific days; others get ``fill(day)``."""
    out = []
    for d in range(1, 22):
        spec = (days or {}).get(d) or {"items": [fill(d) if fill else "c-one"]}
        week = (d - 1) // 7 + 1
        out.append({"day": d, "week": week, "topic": f"주제 {d}", "practice": f"실습 {d}", **spec})
    path = root / "curriculum" / "plan.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"days": out, "extras": list(extras)}, allow_unicode=True))


def make_catalog(root: Path, missions=None, scenarios=None, plan=True) -> Path:
    """Default: warmups m-one, m-two (linux) and concept c-one (network); scenarios given.

    With ``plan=True`` a valid 21-day plan is written: day 1 is c-one, then the given
    scenarios in order (repeating), so every scenario appears.
    """
    missions = (
        missions
        if missions is not None
        else [
            ("linux", mission_spec("m-one")),
            ("linux", mission_spec("m-two")),
            ("network", mission_spec("c-one", kind="concept")),
        ]
    )
    for field_dir, spec in missions:
        write_mission(root, field_dir, spec)
    ids = []
    for spec in scenarios or []:
        write_scenario(root, spec)
        ids.append(spec["id"])
    if plan:
        write_plan(root, fill=(lambda d: ids[(d - 2) % len(ids)] if ids and d > 1 else "c-one"))
    (root / "data").mkdir(exist_ok=True)
    return root


def ev(type_: str, item_id: str, minutes: float = 0, **fields) -> Event:
    return Event(ts=NOW + timedelta(minutes=minutes), type=type_, id=item_id, **fields)


def metrics(**values) -> dict:
    """Full metric dict; given keys are values (or a status string), the rest unavailable."""
    out = {}
    for key in METRIC_KEYS:
        if key in values:
            v = values[key]
            out[key] = {"status": v} if isinstance(v, str) else {"value": v}
        else:
            out[key] = {"status": "unavailable"}
    return out


def measured(item_id: str, minutes: float, attempt: int, phase: str, **values) -> Event:
    return ev("measured", item_id, minutes, attempt=attempt, phase=phase, metrics=metrics(**values))


def progress_of(*events: Event) -> Progress:
    return Progress(events=sorted(events, key=lambda e: e.ts))


@dataclass
class FakeRunner:
    """Scripted exit codes per (item_id, script); default 0. Records every call."""

    codes: dict[tuple[str, str], list[int]] = field(default_factory=dict)
    calls: list[tuple[str, str, tuple[str, ...]]] = field(default_factory=list)
    dirty: list[str] = field(default_factory=list)
    raises: dict[tuple[str, str], Exception] = field(default_factory=dict)

    def set(self, item_id: str, script: str, *codes: int) -> None:
        self.codes[(item_id, script)] = list(codes)

    def run(self, item_id: str, item_dir: Path, script: str, *args: str) -> int:
        self.calls.append((item_id, script, args))
        if (item_id, script) in self.raises:
            raise self.raises[(item_id, script)]
        queue = self.codes.get((item_id, script))
        if queue:
            return queue.pop(0) if len(queue) > 1 else queue[0]
        return 0

    def restore(self, mode: str) -> int:
        return self.run("environment", Path(os.devnull), "restore.sh", mode)

    def mark_dirty(self, env: str) -> None:
        self.dirty.append(env)

    def scripts(self) -> list[str]:
        return [f"{item}:{script}" for item, script, _ in self.calls]


@dataclass
class FakeMeasurer:
    """Returns scripted metric dicts per phase (or raises); records calls."""

    by_phase: dict[str, dict] = field(default_factory=dict)
    calls: list[tuple[str, int, str]] = field(default_factory=list)
    fail: bool = False

    def run(self, scenario, attempt: int, phase: str) -> dict:
        from troubleshoot_lab.measure import MeasureError

        self.calls.append((scenario.id, attempt, phase))
        if self.fail:
            raise MeasureError("k6 failed")
        return self.by_phase.get(phase) or metrics(
            avg_ms=10.0, p95_ms=20.0, rps=100.0, error_rate=0.0, requests=500
        )
