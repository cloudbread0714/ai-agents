"""Load and validate missions, scenarios and the curriculum plan (data-model.md 카탈로그, Plan)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from shared.config import ConfigError, load_yaml
from troubleshoot_lab.models import FIELDS, Mission, Plan, Scenario

MISSION_SCRIPTS = ("setup.sh", "verify.sh")
SCENARIO_SCRIPTS = ("inject.sh", "verify.sh", "reset.sh")
PLAN_FILE = Path("curriculum") / "plan.yaml"
DAY_MINUTES = (60, 90)
_HINT_HEADING = re.compile(r"^## 힌트 (\d+)[ \t]*$", re.M)

Kind = Literal["mission", "scenario", "plan"]


@dataclass(frozen=True)
class CatalogError:
    kind: Kind
    id: str
    message: str

    def __str__(self) -> str:
        return f"{self.kind} {self.id}: {self.message}"


@dataclass
class Catalog:
    root: Path
    missions: dict[str, Mission] = field(default_factory=dict)
    scenarios: dict[str, Scenario] = field(default_factory=dict)
    paths: dict[str, Path] = field(default_factory=dict)
    hints: dict[str, list[str]] = field(default_factory=dict)
    solutions: dict[str, str] = field(default_factory=dict)
    plan: Plan | None = None
    errors: list[CatalogError] = field(default_factory=list)

    def get(self, item_id: str) -> Mission | Scenario | None:
        return self.missions.get(item_id) or self.scenarios.get(item_id)

    def kind(self, item_id: str) -> Literal["mission", "scenario"] | None:
        if item_id in self.missions:
            return "mission"
        if item_id in self.scenarios:
            return "scenario"
        return None

    def error_for(self, item_id: str) -> CatalogError | None:
        return next((e for e in self.errors if e.id == item_id), None)

    def plan_errors(self) -> list[CatalogError]:
        return [e for e in self.errors if e.kind == "plan"]

    def minutes_with_warmups(self, item_id: str, done: set[str] | None = None) -> int:
        """Main item minutes plus its linked warmups not in ``done`` (FR-032)."""
        done = done or set()
        if item_id in self.missions:
            return self.missions[item_id].minutes
        scenario = self.scenarios[item_id]
        extra = sum(
            self.missions[w].minutes
            for w in scenario.warmups
            if w in self.missions and w not in done
        )
        return scenario.minutes + extra


def parse_hints(text: str) -> list[str]:
    """Return the three hint bodies; headings must be exactly ``## 힌트 1``..``## 힌트 3``."""
    matches = list(_HINT_HEADING.finditer(text))
    numbers = [int(m.group(1)) for m in matches]
    if numbers != [1, 2, 3]:
        raise ValueError(f"hints.md needs headings '## 힌트 1'~'## 힌트 3' in order, got {numbers}")
    bodies = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end() : end].strip()
        if not body:
            raise ValueError(f"hints.md: 힌트 {numbers[i]} is empty")
        bodies.append(body)
    return bodies


def _script_problems(item_dir: Path, names: tuple[str, ...]) -> list[str]:
    problems = []
    for name in names:
        path = item_dir / name
        if not path.is_file():
            problems.append(f"missing {name}")
        elif not os.access(path, os.X_OK):
            problems.append(f"{name} is not executable")
    return problems


def _item_dirs(root: Path) -> list[tuple[str, Path]]:
    if not root.is_dir():
        return []
    return [
        (group.name, item)
        for group in sorted(p for p in root.iterdir() if p.is_dir())
        for item in sorted(p for p in group.iterdir() if p.is_dir())
    ]


def _load_yaml[T: (Mission, Scenario)](
    item_dir: Path, yaml_name: str, model: type[T]
) -> tuple[T | None, list[str]]:
    try:
        item = load_yaml(item_dir / yaml_name, model)
    except ConfigError as exc:
        return None, [str(exc).replace(str(item_dir) + "/", "")]
    problems = []
    if item.id != item_dir.name:
        problems.append(f"id '{item.id}' must match the directory name")
    return item, problems


def load_catalog(root: Path) -> Catalog:
    cat = Catalog(root=root)
    seen: set[str] = set()

    for group, item_dir in _item_dirs(root / "missions"):
        problems: list[str] = []
        mission = None
        if group not in FIELDS:
            problems.append(f"unknown field directory '{group}'")
        else:
            mission, problems = _load_yaml(item_dir, "mission.yaml", Mission)
            if mission is not None:
                if mission.field not in (None, group):
                    problems.append(f"field '{mission.field}' does not match directory '{group}'")
                mission = mission.model_copy(update={"field": group})
        problems += _script_problems(item_dir, MISSION_SCRIPTS)
        if item_dir.name in seen:
            problems.append("id is used more than once")
        seen.add(item_dir.name)
        if problems or mission is None:
            cat.errors += [CatalogError("mission", item_dir.name, p) for p in problems]
            continue
        cat.missions[mission.id] = mission
        cat.paths[mission.id] = item_dir

    numbers: dict[str, str] = {}
    for group, item_dir in _item_dirs(root / "scenarios"):
        problems = []
        scenario = None
        if group not in FIELDS:
            problems.append(f"unknown field directory '{group}'")
        else:
            scenario, problems = _load_yaml(item_dir, "scenario.yaml", Scenario)
        problems += _script_problems(item_dir, SCENARIO_SCRIPTS)
        if item_dir.name in seen:
            problems.append("id is used more than once")
        seen.add(item_dir.name)
        hints: list[str] = []
        solution = ""
        try:
            hints = parse_hints((item_dir / "hints.md").read_text(encoding="utf-8"))
        except FileNotFoundError:
            problems.append("missing hints.md")
        except ValueError as exc:
            problems.append(str(exc))
        try:
            solution = (item_dir / "solution.md").read_text(encoding="utf-8").strip()
            if not solution:
                problems.append("solution.md is empty")
        except FileNotFoundError:
            problems.append("missing solution.md")
        if scenario is not None:
            if scenario.fields[0] != group:
                problems.append(f"fields[0] '{scenario.fields[0]}' must match directory '{group}'")
            for w in scenario.warmups:
                if w not in cat.missions:
                    problems.append(f"unknown warmup mission: {w}")
                elif cat.missions[w].kind != "warmup":
                    problems.append(f"warmup {w} is a concept mission")
            if scenario.curriculum_no in numbers:
                problems.append(
                    f"curriculum_no {scenario.curriculum_no} is also used by "
                    f"{numbers[scenario.curriculum_no]}"
                )
        if problems or scenario is None:
            cat.errors += [CatalogError("scenario", item_dir.name, p) for p in problems]
            continue
        numbers[scenario.curriculum_no] = scenario.id
        cat.scenarios[scenario.id] = scenario
        cat.paths[scenario.id] = item_dir
        cat.hints[scenario.id] = hints
        cat.solutions[scenario.id] = solution

    _load_plan(cat)
    return cat


def _load_plan(cat: Catalog) -> None:
    path = cat.root / PLAN_FILE
    if not path.exists():
        cat.errors.append(CatalogError("plan", "plan", f"missing {PLAN_FILE}"))
        return
    try:
        plan = load_yaml(path, Plan)
    except ConfigError as exc:
        cat.errors.append(CatalogError("plan", "plan", str(exc)))
        return
    problems: list[str] = []
    seen: set[str] = set()
    low, high = DAY_MINUTES
    for day in plan.days:
        ids = day.items or day.pool or []
        for pos, item_id in enumerate(ids):
            if item_id in cat.scenarios:
                seen.add(item_id)
            elif item_id in cat.missions:
                if day.pool is not None or pos > 0 or cat.missions[item_id].kind != "concept":
                    problems.append(
                        f"day {day.day}: mission {item_id} must be a concept day's only item"
                    )
                    continue
            else:
                problems.append(f"day {day.day}: unknown item {item_id}")
                continue
        checked = ids if day.pool is not None else ids[:1]
        for item_id in checked:
            if cat.get(item_id) is None:
                continue
            minutes = cat.minutes_with_warmups(item_id)
            if not low <= minutes <= high:
                problems.append(f"day {day.day}: {item_id} takes {minutes} min (need {low}–{high})")
    for item_id in plan.extras:
        if item_id not in cat.scenarios:
            problems.append(f"extras: unknown scenario {item_id}")
        elif item_id in seen:
            problems.append(f"extras: {item_id} is already in the days")
        seen.add(item_id)
    missing = sorted(set(cat.scenarios) - seen)
    if missing:
        problems.append(f"scenarios not in the plan: {', '.join(missing)}")
    cat.errors += [CatalogError("plan", "plan", p) for p in problems]
    if not problems:
        cat.plan = plan
