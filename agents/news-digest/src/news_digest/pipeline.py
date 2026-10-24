"""End-to-end run: collect → select → post (data-model.md, RunResult state transitions)."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TextIO
from zoneinfo import ZoneInfo

import httpx

from news_digest import history
from news_digest.alerts import build_alert_payload, build_warning_payload
from news_digest.balance import preferred_category
from news_digest.collector import collect
from news_digest.formatter import build_post_payload
from news_digest.models import PostRecord, RunResult, RunStatus, Settings, SourcesFile
from news_digest.normalize import dedupe, limit_candidates
from news_digest.selector import BudgetExceeded, SelectionError, select
from shared.logging import get_logger
from shared.slack import SlackSendError, send_webhook

log = get_logger(__name__)

Target = Literal["main", "test"]

# Statuses that end the run without a main-channel post and need a test-channel alert.
_ALERT_STATUSES = {
    RunStatus.COLLECT_FAILED,
    RunStatus.NO_NEW_ARTICLES,
    RunStatus.BUDGET_EXCEEDED,
    RunStatus.SELECT_FAILED,
    RunStatus.POST_FAILED,
}


@dataclass
class RunContext:
    settings: Settings
    sources: SourcesFile
    env: Mapping[str, str]
    http: httpx.Client
    llm: Any
    now: datetime
    history_path: Path
    target: Target = "main"
    dry_run: bool = False
    force: bool = False
    out: TextIO = sys.stdout
    base_delay: float = 1.0


def _webhook(ctx: RunContext, target: Target) -> str:
    key = "SLACK_WEBHOOK_URL_MAIN" if target == "main" else "SLACK_WEBHOOK_URL_TEST"
    return ctx.env[key]


def _deliver(ctx: RunContext, target: Target, payload: dict) -> None:
    if ctx.dry_run:
        _print_payload(ctx.out, payload)
        return
    send_webhook(_webhook(ctx, target), payload, client=ctx.http, base_delay=ctx.base_delay)


def _print_payload(out: TextIO, payload: dict) -> None:
    for block in payload.get("blocks", []):
        text = block.get("text", {}).get("text")
        if text is None and block.get("elements"):
            text = " ".join(e.get("text", "") for e in block["elements"])
        if text:
            print(text, file=out)
    print(file=out)


def _notify(ctx: RunContext, payload: dict) -> None:
    """Send to the test channel; a failure here is logged, never raised."""
    try:
        _deliver(ctx, "test", payload)
    except SlackSendError as exc:
        log.error("alert_failed", extra={"fields": {"error": str(exc)}})


def _records_history(ctx: RunContext) -> bool:
    return ctx.target == "main" and not ctx.dry_run


def run(ctx: RunContext) -> RunResult:
    result = RunResult(run_at=ctx.now)
    try:
        _run(ctx, result)
    except Exception as exc:  # noqa: BLE001 - last line of defence: alert, then exit 1
        log.exception("unexpected_error")
        result.status, result.stage = None, result.stage or "unknown"
        result.error = f"{type(exc).__name__}: {exc}"

    tz, env = ctx.settings.timezone, ctx.env
    if result.status is None or result.status in _ALERT_STATUSES:
        _notify(ctx, build_alert_payload(result, tz=tz, env=env))
    elif result.status == RunStatus.POSTED and result.warnings:
        _notify(ctx, build_warning_payload(result, tz=tz, env=env))

    log.info("run_finished", extra={"fields": json.loads(json.dumps(result.summary()))})
    return result


def _fail(result: RunResult, status: RunStatus, stage: str, error: str) -> None:
    result.status, result.stage, result.error = status, stage, error


def _run(ctx: RunContext, result: RunResult) -> None:
    settings = ctx.settings
    today_kst = ctx.now.astimezone(ZoneInfo(settings.timezone)).date()
    result.stage = "history"
    posted = history.load(ctx.history_path)

    if history.posted_today(posted, today_kst) and not ctx.force:
        result.status, result.stage = RunStatus.ALREADY_POSTED, None
        return

    # --- collect ------------------------------------------------------------------------
    result.stage = "collect"
    articles, result.source_results = collect(
        ctx.sources.enabled, settings, ctx.now, ctx.http, base_delay=ctx.base_delay
    )
    failed = result.failed_sources
    if failed and len(failed) == len(result.source_results):
        return _fail(
            result, RunStatus.COLLECT_FAILED, "collect", f"all {len(failed)} sources failed"
        )
    if failed:
        result.warnings.append(f"partial collect: {', '.join(failed)}")

    already = history.posted_ids(posted)
    fresh = [a for a in dedupe(articles) if a.id not in already]
    candidates = limit_candidates(fresh, settings.selection.max_candidates)
    result.candidate_count = len(candidates)
    if not candidates:
        return _fail(
            result,
            RunStatus.NO_NEW_ARTICLES,
            "collect",
            f"no unposted articles in the last {settings.selection.freshness_hours}h",
        )

    # --- select -------------------------------------------------------------------------
    result.stage = "select"
    window = settings.selection.balance_window
    recent = history.recent_categories(posted, window)
    preferred = preferred_category(recent, window)
    try:
        outcome = select(
            ctx.llm,
            settings,
            candidates,
            today_kst=today_kst,
            recent_categories=recent,
            preferred=preferred,
        )
    except BudgetExceeded as exc:
        return _fail(result, RunStatus.BUDGET_EXCEEDED, "budget", str(exc))
    except SelectionError as exc:
        return _fail(result, RunStatus.SELECT_FAILED, "select", str(exc))

    selection = outcome.selection
    result.selected = selection
    result.estimated_cost_usd = outcome.estimated_cost_usd
    result.actual_cost_usd = outcome.actual_cost_usd
    if preferred and selection.category != preferred and not selection.balance_override_reason:
        log.warning(
            "balance_override_without_reason",
            extra={"fields": {"preferred": preferred, "selected": selection.category}},
        )
    if selection.low_relevance:
        result.warnings.append("low relevance: 모든 후보의 관심 분야 관련도가 낮음")

    # --- post ---------------------------------------------------------------------------
    result.stage = "post"
    payload = build_post_payload(
        selection, outcome.article, today_kst, test_mode=ctx.target == "test"
    )
    try:
        _deliver(ctx, ctx.target, payload)
    except SlackSendError as exc:
        return _fail(result, RunStatus.POST_FAILED, "post", str(exc))

    # FR-018: history changes only after the main-channel post is confirmed.
    if _records_history(ctx):
        result.stage = "history"
        record = PostRecord(
            article_id=outcome.article.id,
            url=outcome.article.normalized_url,
            title=outcome.article.title,
            title_ko=selection.title_ko,
            category=selection.category,
            source=outcome.article.source,
            posted_at=ctx.now,
            posted_date_kst=today_kst,
        )
        history.save(ctx.history_path, history.append(posted, record), now=ctx.now)
    result.status, result.stage = RunStatus.POSTED, None
