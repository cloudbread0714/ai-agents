"""Daily problem and Sunday summary posting (contracts/cli.md 게시 명령).

Dates and weekdays are always KST: the cron runs at 23:40 UTC, which is already the
next day in Korea (research R8).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import IO, Any, Literal

import httpx

from shared.alerts import alert_payload, warning_payload
from shared.logging import get_logger
from shared.slack import SlackSendError, send_webhook
from troubleshoot_lab import posted as posted_mod
from troubleshoot_lab.catalog import load_catalog
from troubleshoot_lab.messages import build_daily, build_weekly
from troubleshoot_lab.models import DailyPost, WeeklyPost
from troubleshoot_lab.planner import plan_today
from troubleshoot_lab.progress import ProgressStore
from troubleshoot_lab.weekly import KST, summarize, week_start

log = get_logger(__name__)

AGENT = "troubleshoot-lab"
LAB_WEBHOOK = "SLACK_WEBHOOK_LAB_URL"
TEST_WEBHOOK = "SLACK_WEBHOOK_URL_TEST"

Target = Literal["test", "lab"]
PostMode = Literal["daily", "weekly", "both"]


class RunStatus(StrEnum):
    POSTED = "POSTED"
    ALREADY_POSTED = "ALREADY_POSTED"
    NO_SCENARIO = "NO_SCENARIO"
    POST_FAILED = "POST_FAILED"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"


FAILURES = {RunStatus.NO_SCENARIO, RunStatus.POST_FAILED, RunStatus.UNEXPECTED_ERROR}


@dataclass
class RunContext:
    lab_root: Path
    env: Mapping[str, str]
    http: httpx.Client
    now: datetime
    target: Target = "test"
    dry_run: bool = False
    force: bool = False
    post: PostMode = "daily"
    out: IO[str] | None = None
    base_delay: float = 1.0


@dataclass
class PartResult:
    status: RunStatus
    kind: str | None = None
    day: int | None = None
    main_id: str | None = None
    second_id: str | None = None
    backlog: list[str] | None = None
    error: str | None = None


@dataclass
class RunResult:
    status: RunStatus
    stage: str | None = None
    daily: PartResult | None = None
    weekly: PartResult | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "daily": asdict(self.daily) if self.daily else None,
            "weekly": asdict(self.weekly) if self.weekly else None,
            "warnings": self.warnings,
            "error": self.error,
        }


def exit_code(result: RunResult) -> int:
    return 1 if result.status in FAILURES else 0


def run(ctx: RunContext) -> RunResult:
    try:
        result = _run(ctx)
    except Exception as exc:  # noqa: BLE001 - every failure must reach the test channel
        log.exception("unexpected_error")
        result = RunResult(
            RunStatus.UNEXPECTED_ERROR, stage="unexpected", error=f"{type(exc).__name__}: {exc}"
        )
    if result.status in FAILURES:
        _notify(ctx, _alert(ctx, result))
    log.info("run_finished", extra={"fields": result.summary()})
    return result


def _run(ctx: RunContext) -> RunResult:
    catalog = load_catalog(ctx.lab_root)
    progress = ProgressStore(ctx.lab_root / "data" / "progress.json").load()
    posted_path = ctx.lab_root / "data" / "posted.json"
    posted = posted_mod.load(posted_path)
    result = RunResult(RunStatus.ALREADY_POSTED)
    if catalog.errors:
        result.warnings = [f"유효하지 않은 항목 제외: {e}" for e in catalog.errors]
        _notify(
            ctx,
            warning_payload(
                AGENT,
                result.warnings,
                context_parts=_context(ctx),
                env=ctx.env,
                note="유효한 항목으로만 진행",
            ),
        )

    today = ctx.now.astimezone(KST).date()
    is_sunday = today.weekday() == 6
    do_daily = ctx.post in ("daily", "both")
    do_weekly = ctx.post in ("weekly", "both") or (ctx.post == "daily" and is_sunday)
    record = ctx.target == "lab" and not ctx.dry_run
    changed = False

    if do_daily:
        if not ctx.force and posted_mod.posted_on(posted, today):
            result.daily = PartResult(RunStatus.ALREADY_POSTED)
        elif (choice := plan_today(catalog, progress, posted, today)) is None:
            result.daily = PartResult(
                RunStatus.NO_SCENARIO, error="게시할 수 있는 학습 항목이 없어요(카탈로그·계획 확인)"
            )
        else:
            payload = build_daily(choice, catalog, progress, today, test_mode=ctx.target == "test")
            error = _deliver(ctx, payload)
            result.daily = PartResult(
                RunStatus.POST_FAILED if error else RunStatus.POSTED,
                kind=choice.kind,
                day=choice.day,
                main_id=choice.main_id,
                second_id=choice.second_id,
                backlog=choice.backlog,
                error=error,
            )
            if not error and record and not posted_mod.posted_on(posted, today):
                posted.daily.append(
                    DailyPost(
                        date_kst=today,
                        kind=choice.kind,
                        day=choice.day,
                        main_kind=choice.main_kind,
                        main_id=choice.main_id,
                        second_id=choice.second_id,
                        posted_at=ctx.now,
                    )
                )
                changed = True

    if do_weekly:
        start = week_start(ctx.now)
        if not ctx.force and posted_mod.weekly_posted(posted, start):
            result.weekly = PartResult(RunStatus.ALREADY_POSTED)
        else:
            summary = summarize(catalog, progress, posted, ctx.now, ctx.lab_root.parents[1])
            error = _deliver(ctx, build_weekly(summary, test_mode=ctx.target == "test"))
            result.weekly = PartResult(
                RunStatus.POST_FAILED if error else RunStatus.POSTED, error=error
            )
            if not error and record and not posted_mod.weekly_posted(posted, start):
                posted.weekly.append(WeeklyPost(week_start_kst=start, posted_at=ctx.now))
                changed = True

    if changed:
        posted_mod.save(posted_path, posted, now=ctx.now)

    parts = [p for p in (result.daily, result.weekly) if p]
    failed = [p for p in parts if p.status in FAILURES]
    if failed:
        result.status = failed[0].status
        result.stage = "select" if failed[0].status == RunStatus.NO_SCENARIO else "post"
        result.error = failed[0].error
    elif any(p.status == RunStatus.POSTED for p in parts):
        result.status = RunStatus.POSTED
    return result


def _webhook(ctx: RunContext) -> str:
    return ctx.env[LAB_WEBHOOK if ctx.target == "lab" else TEST_WEBHOOK]


def _deliver(ctx: RunContext, payload: dict[str, Any]) -> str | None:
    """Send (or print in dry-run). Returns an error string on failure."""
    if ctx.dry_run:
        _print(ctx, payload)
        return None
    try:
        send_webhook(_webhook(ctx), payload, client=ctx.http, base_delay=ctx.base_delay)
    except SlackSendError as exc:
        return str(exc)
    return None


def _notify(ctx: RunContext, payload: dict[str, Any]) -> None:
    """Alerts and warnings always go to the test channel; never raise."""
    if ctx.dry_run:
        _print(ctx, payload)
        return
    try:
        send_webhook(ctx.env[TEST_WEBHOOK], payload, client=ctx.http, base_delay=ctx.base_delay)
    except (SlackSendError, KeyError) as exc:
        log.error("alert_failed", extra={"fields": {"error": str(exc)}})


def _context(ctx: RunContext) -> list[str]:
    at = ctx.now.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
    return [f"실행: {at}", f"대상: {ctx.target}"]


def _alert(ctx: RunContext, result: RunResult) -> dict[str, Any]:
    return alert_payload(
        AGENT,
        result.status.value,
        stage=result.stage,
        cause=result.error,
        context_parts=_context(ctx),
        env=ctx.env,
    )


def _print(ctx: RunContext, payload: dict[str, Any]) -> None:
    if ctx.out is None:
        return
    lines = []
    for block in payload["blocks"]:
        if "text" in block:
            lines.append(block["text"]["text"])
        lines += [el["text"] for el in block.get("elements", [])]
    ctx.out.write("\n".join(lines) + "\n\n")


def summary_json(result: RunResult) -> str:
    return json.dumps(result.summary(), ensure_ascii=False)
