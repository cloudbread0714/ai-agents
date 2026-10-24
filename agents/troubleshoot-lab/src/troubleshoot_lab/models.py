"""Catalog, plan, progress and posting models (data-model.md, curriculum revision)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

ID_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
CURRICULUM_NO_PATTERN = r"^(\d{1,2}(-[A-Z])?|extra-\d+)$"

LabField = Literal["network", "linux", "webserver", "db-cache", "lb-cloud", "monitoring"]
FIELDS: tuple[LabField, ...] = (
    "network",
    "linux",
    "webserver",
    "db-cache",
    "lb-cloud",
    "monitoring",
)
FIELD_LABEL: dict[str, str] = {
    "network": "① 네트워크",
    "linux": "② 리눅스 서버",
    "webserver": "③ 웹 서버와 소켓",
    "db-cache": "④ 데이터베이스와 캐시",
    "lb-cloud": "⑤ 부하 분산과 클라우드",
    "monitoring": "⑥ 모니터링과 장애 대응",
}

Env = Literal["compose", "kind"]
MissionKind = Literal["warmup", "concept"]

Difficulty = Literal["beginner", "intermediate", "advanced"]
DIFFICULTY_RANK: dict[str, int] = {"beginner": 0, "intermediate": 1, "advanced": 2}
DIFFICULTY_LABEL: dict[str, str] = {"beginner": "초급", "intermediate": "중급", "advanced": "고급"}

Phase = Literal["baseline", "fault", "after"]
PHASE_LABEL: dict[str, str] = {"baseline": "정상 상태", "fault": "장애 상태", "after": "해결 후"}
MetricStatus = Literal["unavailable", "skipped", "not_applicable"]
METRIC_KEYS: tuple[str, ...] = (
    "avg_ms",
    "p95_ms",
    "rps",
    "error_rate",
    "requests",
    "cpu_avg_pct",
    "cpu_max_pct",
    "mem_max_mib",
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- catalog (YAML written by people) -------------------------------------------------


class MissionStep(_Strict):
    id: str = Field(pattern=ID_PATTERN)
    guide: str = Field(min_length=1)
    command: str = Field(min_length=1)
    check: Literal["state", "answer"]
    prompt: str | None = None

    @model_validator(mode="after")
    def _answer_needs_prompt(self) -> MissionStep:
        if self.check == "answer" and not self.prompt:
            raise ValueError(f"step {self.id}: check=answer requires a prompt")
        return self


class Mission(_Strict):
    id: str = Field(pattern=ID_PATTERN)
    field: LabField | None = None  # taken from the directory when omitted
    env: Env
    kind: MissionKind = "warmup"
    title: str = Field(min_length=1, max_length=60)
    minutes: int
    goals: list[str] = Field(min_length=1, max_length=5)
    steps: list[MissionStep] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def _rules(self) -> Mission:
        ids = [s.id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("step ids must be unique")
        low, high = (30, 90) if self.kind == "concept" else (5, 60)
        if not low <= self.minutes <= high:
            raise ValueError(f"minutes must be {low}–{high} for kind={self.kind}")
        return self


class MeasureSpec(_Strict):
    method: Literal["GET", "POST"] = "GET"
    path: str = Field(pattern=r"^/[^\s]*$")
    scheme: Literal["http", "https"] = "http"
    body: str | None = None
    vus: int = Field(default=5, ge=1, le=50)
    duration_s: int = Field(default=20, ge=5, le=40)
    service: str = Field(min_length=1, pattern=ID_PATTERN)

    @model_validator(mode="after")
    def _internal_only(self) -> MeasureSpec:
        if "://" in self.path:  # hosts are fixed by env (FR-027)
            raise ValueError("measure.path must be a path, not a URL")
        return self


class Scenario(_Strict):
    id: str = Field(pattern=ID_PATTERN)
    curriculum_no: str = Field(pattern=CURRICULUM_NO_PATTERN)
    fields: list[LabField] = Field(min_length=1, max_length=3)
    env: Env
    title: str = Field(min_length=1, max_length=60)
    difficulty: Difficulty
    minutes: int = Field(ge=20, le=90)
    symptom: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)  # authors only; never published
    warmups: list[str] = Field(min_length=1, max_length=2)
    start_hint: str | None = None
    measure: MeasureSpec
    interview: list[str] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def _rules(self) -> Scenario:
        if len(set(self.fields)) != len(self.fields):
            raise ValueError("fields must be unique")
        if any(not 1 <= len(q) <= 200 for q in self.interview):
            raise ValueError("each interview question must be 1–200 characters")
        return self

    @property
    def field(self) -> str:
        return self.fields[0]


# --- curriculum plan (curriculum/plan.yaml) -------------------------------------------


class PlanDay(_Strict):
    day: int = Field(ge=1, le=21)
    week: int = Field(ge=1, le=3)
    topic: str = Field(min_length=1)
    practice: str = Field(min_length=1)
    items: list[str] | None = Field(default=None, min_length=1, max_length=2)
    pool: list[str] | None = Field(default=None, min_length=2, max_length=6)

    @model_validator(mode="after")
    def _items_or_pool(self) -> PlanDay:
        if (self.items is None) == (self.pool is None):
            raise ValueError(f"day {self.day}: exactly one of items or pool is required")
        return self


class Plan(_Strict):
    days: list[PlanDay]
    extras: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _all_days(self) -> Plan:
        if [d.day for d in self.days] != list(range(1, 22)):
            raise ValueError("days must be 1..21 in order")
        return self

    def get(self, day: int) -> PlanDay:
        return self.days[day - 1]


# --- progress (data/progress.json, version 2) -----------------------------------------

EventType = Literal[
    "mission_completed",
    "scenario_started",
    "measured",
    "fault_injected",
    "hint_opened",
    "scenario_solved",
    "scenario_gave_up",
    "scenario_reset",
    "report_completed",
]


class Metric(_Strict):
    value: float | None = None
    status: MetricStatus | None = None

    @model_validator(mode="after")
    def _one(self) -> Metric:
        if (self.value is None) == (self.status is None):
            raise ValueError("a metric has exactly one of value or status")
        return self


_NEEDS_ATTEMPT = {
    "scenario_started",
    "measured",
    "fault_injected",
    "hint_opened",
    "scenario_solved",
    "scenario_gave_up",
    "scenario_reset",
    "report_completed",
}


class Event(_Strict):
    ts: AwareDatetime
    type: EventType
    id: str = Field(pattern=ID_PATTERN)
    attempt: int | None = Field(default=None, ge=1)
    phase: Phase | None = None
    metrics: dict[str, Metric] | None = None
    skip_reason: str | None = Field(default=None, min_length=1, max_length=200)
    level: int | None = Field(default=None, ge=1, le=3)
    hints_used: int | None = Field(default=None, ge=0, le=3)
    was_active: bool | None = None
    report: str | None = Field(
        default=None, pattern=r"^agents/troubleshoot-lab/docs/reports/.+\.md$"
    )
    answered: int | None = Field(default=None, ge=0, le=2)

    @model_validator(mode="after")
    def _required_fields(self) -> Event:
        if self.type in _NEEDS_ATTEMPT and self.attempt is None:
            raise ValueError(f"{self.type} requires attempt")
        if self.type == "hint_opened" and self.level is None:
            raise ValueError("hint_opened requires level")
        if self.type in ("scenario_solved", "scenario_gave_up") and self.hints_used is None:
            raise ValueError(f"{self.type} requires hints_used")
        if self.type == "measured":
            if self.phase is None or self.metrics is None:
                raise ValueError("measured requires phase and metrics")
            if set(self.metrics) != set(METRIC_KEYS):
                raise ValueError(f"measured metrics must be exactly {', '.join(METRIC_KEYS)}")
        if self.type == "report_completed" and (self.report is None or self.answered is None):
            raise ValueError("report_completed requires report and answered")
        return self


class Progress(_Strict):
    version: Literal[2] = 2
    events: list[Event] = Field(default_factory=list)


# --- posting record (data/posted.json, version 2) -------------------------------------


class DailyPost(_Strict):
    date_kst: date
    kind: Literal["day", "catchup", "extra", "review"]
    day: int | None = Field(default=None, ge=1, le=21)
    main_kind: Literal["scenario", "mission"]
    main_id: str
    second_id: str | None = None
    posted_at: AwareDatetime

    @model_validator(mode="after")
    def _day_rule(self) -> DailyPost:
        if (self.kind == "day") != (self.day is not None):
            raise ValueError("day is set exactly when kind=day")
        return self


class WeeklyPost(_Strict):
    week_start_kst: date
    posted_at: AwareDatetime


class Posted(_Strict):
    version: Literal[2] = 2
    daily: list[DailyPost] = Field(default_factory=list)
    weekly: list[WeeklyPost] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_dates(self) -> Posted:
        days = [d.date_kst for d in self.daily]
        weeks = [w.week_start_kst for w in self.weekly]
        if len(days) != len(set(days)):
            raise ValueError("daily.date_kst must be unique")
        if len(weeks) != len(set(weeks)):
            raise ValueError("weekly.week_start_kst must be unique")
        return self
