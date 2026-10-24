"""Entities from specs/001-news-daily-digest/data-model.md."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

from shared.llm import Price

Category = Literal["infra", "ai_agent"]
SourceCategory = Literal["infra", "ai_agent", "auto"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]


# --- Config ---------------------------------------------------------------------------


class Source(BaseModel):
    name: str = Field(min_length=1)
    url: str
    category: SourceCategory
    enabled: bool = True
    max_items: int | None = Field(default=None, ge=1)

    @field_validator("url")
    @classmethod
    def _http_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must be http(s)")
        return v


class SourcesFile(BaseModel):
    sources: list[Source]

    @model_validator(mode="after")
    def _check(self) -> SourcesFile:
        names = [s.name for s in self.sources]
        if dupes := sorted({n for n in names if names.count(n) > 1}):
            raise ValueError(f"duplicate source names: {', '.join(dupes)}")
        if not any(s.enabled for s in self.sources):
            raise ValueError("at least one source must be enabled")
        return self

    @property
    def enabled(self) -> list[Source]:
        return [s for s in self.sources if s.enabled]


class InterestProfile(BaseModel):
    infra: list[str]
    ai_agent: list[str]
    career: list[str] = []


class SelectionSettings(BaseModel):
    priority: list[str] = ["relevance", "practical_impact", "learning_value"]
    freshness_hours: int = Field(default=72, ge=24)
    max_items_per_source: int = Field(default=15, ge=1)
    max_candidates: int = Field(default=40, ge=1)
    balance_window: int = Field(default=2, ge=1)


class LLMSettings(BaseModel):
    model: str
    effort: Effort = "medium"
    max_tokens: int = Field(default=4000, ge=256)
    max_retries: int = Field(default=3, ge=0)
    fallbacks: Literal["default"] | None = "default"


class BudgetSettings(BaseModel):
    max_cost_usd_per_run: float = Field(gt=0)


class Settings(BaseModel):
    interests: InterestProfile
    selection: SelectionSettings = SelectionSettings()
    llm: LLMSettings
    budget: BudgetSettings
    pricing: dict[str, Price]
    timezone: str = "Asia/Seoul"

    @model_validator(mode="after")
    def _model_has_pricing(self) -> Settings:
        if self.llm.model not in self.pricing:
            raise ValueError(f"llm.model {self.llm.model!r} must have an entry in pricing")
        return self


# --- Collection -----------------------------------------------------------------------


class Article(BaseModel):
    id: str = Field(pattern=r"^[0-9a-f]{16}$")
    title: str = Field(max_length=300)
    url: str
    normalized_url: str
    source: str
    category_hint: SourceCategory
    published_at: AwareDatetime
    published_inferred: bool = False
    excerpt: str = Field(default="", max_length=300)


class SourceResult(BaseModel):
    source: str
    ok: bool
    item_count: int = 0
    error: str | None = None


# --- Selection & posting --------------------------------------------------------------


class DigestSelection(BaseModel):
    """Structured output contract for the Claude selection call (contracts/llm-output.md)."""

    selected_id: str = Field(description="id attribute of the chosen <candidate>")
    category: Category = Field(description="infra or ai_agent")
    title_ko: str = Field(max_length=80, description="한 줄 한국어 제목")
    summary_ko: list[str] = Field(min_length=3, max_length=5, description="핵심 요약 3~5줄")
    apply_points_ko: list[str] = Field(
        min_length=1, max_length=2, description="관심 분야에 적용할 기술·아이디어 1~2개"
    )
    selection_reason: str
    balance_override_reason: str | None = None
    low_relevance: bool = False


class PostRecord(BaseModel):
    article_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    url: str
    title: str
    title_ko: str
    category: Category
    source: str
    posted_at: AwareDatetime
    posted_date_kst: date


class History(BaseModel):
    version: Literal[1] = 1
    posts: list[PostRecord] = []


# --- Run ------------------------------------------------------------------------------


class RunStatus(StrEnum):
    POSTED = "POSTED"
    ALREADY_POSTED = "ALREADY_POSTED"
    COLLECT_FAILED = "COLLECT_FAILED"
    NO_NEW_ARTICLES = "NO_NEW_ARTICLES"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    SELECT_FAILED = "SELECT_FAILED"
    POST_FAILED = "POST_FAILED"


class RunResult(BaseModel):
    run_at: datetime
    status: RunStatus | None = None
    stage: str | None = None
    source_results: list[SourceResult] = []
    candidate_count: int = 0
    selected: DigestSelection | None = None
    estimated_cost_usd: float | None = None
    actual_cost_usd: float | None = None
    warnings: list[str] = []
    error: str | None = None

    @property
    def failed_sources(self) -> list[str]:
        return [r.source for r in self.source_results if not r.ok]

    def summary(self) -> dict:
        return {
            "status": self.status,
            "candidate_count": self.candidate_count,
            "selected_id": self.selected.selected_id if self.selected else None,
            "estimated_cost_usd": self.estimated_cost_usd,
            "actual_cost_usd": self.actual_cost_usd,
            "warnings": self.warnings,
            "error": self.error,
        }
