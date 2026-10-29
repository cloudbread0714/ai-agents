"""Posting, application folder metadata, render issues and the edit plan (data-model.md)."""

from __future__ import annotations

import json
from datetime import date, datetime
from functools import cache
from pathlib import Path
from typing import Literal

import jsonschema
from pydantic import BaseModel, ConfigDict, Field, model_validator

from job_apply.errors import PlanError

SCHEMA_PATH = Path(__file__).parent / "schema" / "tailor-plan.schema.json"

Origin = Literal["slack", "direct"]
Status = Literal["in_progress", "done", "failed"]
IssueKind = Literal["overflow", "offslide", "overlap", "visual"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- posting (.job-state/inbox/<id>.json) -----------------------------------------------


class FetchInfo(_Model):
    status: Literal["ok", "failed", "skipped"]
    reason: str | None = None


class Posting(_Model):
    id: str
    origin: Origin
    message_ts: str | None = None
    posted_at: datetime | None = None
    url: str | None = None
    extra_urls: list[str] = Field(default_factory=list)
    url_key: str
    fetch: FetchInfo
    company: str | None = None
    role: str | None = None
    deadline: date | None = None
    duplicate_of: str | None = None

    def expired(self, today: date) -> bool:
        return self.deadline is not None and self.deadline < today


# --- application folder (meta.json) -----------------------------------------------------


class PostingRef(_Model):
    id: str
    origin: Origin
    message_ts: str | None = None
    url: str | None = None
    extra_urls: list[str] = Field(default_factory=list)
    url_key: str
    company: str
    role: str
    deadline: date | None = None


class SourceInfo(_Model):
    sha256: str
    mtime: datetime


class Sources(_Model):
    resume: SourceInfo
    portfolio: SourceInfo


class RenderIssue(_Model):
    slide: int = Field(ge=1)
    shape_id: int | None = None
    kind: IssueKind
    detail: str


class RenderState(_Model):
    attempts: int = Field(default=0, ge=0)
    remaining_issues: list[RenderIssue] = Field(default_factory=list)


class SlackProgress(_Model):
    reply_ts: str | None = None
    files_uploaded: bool = False
    reacted: bool = False


class MetaError(_Model):
    step: str
    reason: str


TRANSITIONS: dict[Status, set[Status]] = {
    "in_progress": {"done", "failed", "in_progress"},
    "failed": {"in_progress"},
    "done": set(),
}


class Meta(_Model):
    schema_: Literal[1] = Field(default=1, alias="schema")
    status: Status
    created_at: datetime
    completed_at: datetime | None = None
    posting: PostingRef
    sources: Sources
    fit_score: int | None = Field(default=None, ge=0, le=100)
    render: RenderState = Field(default_factory=RenderState)
    slack: SlackProgress = Field(default_factory=SlackProgress)
    error: MetaError | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    def move(self, status: Status) -> None:
        if status not in TRANSITIONS[self.status]:
            raise ValueError(f"meta.status {self.status} → {status} is not allowed")
        self.status = status

    def dump(self) -> str:
        return self.model_dump_json(indent=2, by_alias=True) + "\n"


# --- tailor.json ------------------------------------------------------------------------


class EditOp(_Model):
    kind: Literal["insert_after", "delete"]
    text: str | None = None


class PortfolioEdit(_Model):
    slide: int = Field(ge=1)
    shape_id: int = Field(ge=0)
    paragraph: int = Field(ge=0)
    text: str | None = None
    runs: list[str] | None = None
    op: EditOp | None = None
    source: str
    reason: str

    @model_validator(mode="after")
    def _one_change(self) -> PortfolioEdit:
        given = [x is not None for x in (self.text, self.runs, self.op)]
        if sum(given) != 1:
            raise ValueError("exactly one of text, runs, op is required")
        if self.op and self.op.kind == "insert_after" and self.op.text is None:
            raise ValueError("op insert_after needs text")
        return self


class ResumeChange(_Model):
    section: str
    before: str | None = None
    after: str
    source: str
    reason: str


class ResumePlan(_Model):
    changes: list[ResumeChange]


class PortfolioPlan(_Model):
    slide_order: list[int]
    order_reason: str | None = None
    edits: list[PortfolioEdit]


class Acknowledged(_Model):
    file: Literal["resume.md", "portfolio.pptx"]
    token: str
    source: str
    reason: str


class TailorPlan(_Model):
    schema_: Literal[1] = Field(alias="schema")
    acknowledged_warnings: list[Acknowledged] = Field(default_factory=list)
    resume: ResumePlan
    portfolio: PortfolioPlan

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


@cache
def _validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def parse_plan(data: object, slide_count: int) -> TailorPlan:
    """Schema check, then the rules the schema cannot express (contracts/cli.md apply 1)."""
    errors = sorted(_validator().iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        lines = [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}" for e in errors]
        raise PlanError("tailor.json 형식 오류\n" + "\n".join(lines[:20]))
    try:
        plan = TailorPlan.model_validate(data)
    except ValueError as exc:
        raise PlanError(f"tailor.json 형식 오류\n{exc}") from None
    order = plan.portfolio.slide_order
    if sorted(order) != list(range(1, slide_count + 1)):
        raise PlanError(
            f"tailor.json: slide_order는 1..{slide_count}의 순열이어야 해요 (받은 값: {order})"
        )
    for i, edit in enumerate(plan.portfolio.edits):
        if edit.slide > slide_count:
            raise PlanError(f"tailor.json: edits[{i}] 슬라이드 {edit.slide}이(가) 없어요")
    return plan


def load_plan(path: Path, slide_count: int) -> TailorPlan:
    if not path.is_file():
        raise PlanError(f"{path.name}이(가) 없어요")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlanError(f"tailor.json JSON 오류: {exc}") from None
    return parse_plan(data, slide_count)
