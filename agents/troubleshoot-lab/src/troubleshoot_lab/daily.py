"""Daily problem and Sunday summary posting (contracts/cli.md 게시 명령).

Dates and weekdays are always KST: the cron runs at 23:40 UTC, which is already the
next day in Korea (research R8).

Solve-gated posting (004 contracts/cli.md): the lab channel always has at most one open
problem. A morning run posts the next one only after ✅ appears on the open problem's
message; otherwise it leaves one reminder a day in that message's thread.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import IO, Any, Literal

import httpx

from shared.alerts import alert_payload, warning_payload
from shared.logging import get_logger
from shared.slack import (
    SlackApiError,
    SlackMessageGone,
    SlackSendError,
    auth_test,
    get_reactions,
    post_message,
    send_webhook,
)
from troubleshoot_lab import gate
from troubleshoot_lab import posted as posted_mod
from troubleshoot_lab import progress as prog
from troubleshoot_lab.catalog import Catalog, load_catalog
from troubleshoot_lab.messages import build_daily, build_reminder, build_weekly
from troubleshoot_lab.models import DailyPost, Posted, Progress, WeeklyPost
from troubleshoot_lab.planner import DayPick, plan_today
from troubleshoot_lab.progress import ProgressStore
from troubleshoot_lab.weekly import KST, summarize, week_start

log = get_logger(__name__)

AGENT = "troubleshoot-lab"
BOT_TOKEN = "SLACK_BOT_TOKEN"
LAB_CHANNEL = "SLACK_LAB_CHANNEL_ID"
LEARNER = "SLACK_USER_ID"
TEST_WEBHOOK = "SLACK_WEBHOOK_URL_TEST"
LAB_ENV = (BOT_TOKEN, LAB_CHANNEL, LEARNER)

Target = Literal["test", "lab"]
PostMode = Literal["daily", "weekly", "both"]


class RunStatus(StrEnum):
    POSTED = "POSTED"
    REMINDED = "REMINDED"
    REPOSTED = "REPOSTED"
    ALREADY_POSTED = "ALREADY_POSTED"
    ALREADY_REMINDED = "ALREADY_REMINDED"
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
    resolved_id: str | None = None
    hint_included: bool | None = None
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


@dataclass
class _State:
    catalog: Catalog
    progress: Progress
    posted: Posted
    today: date


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
    state = _State(catalog, progress, posted, today)
    is_sunday = today.weekday() == 6
    do_daily = ctx.post in ("daily", "both")
    do_weekly = ctx.post in ("weekly", "both") or (ctx.post == "daily" and is_sunday)
    record = ctx.target == "lab" and not ctx.dry_run
    changed = False

    if do_daily:
        if record:
            result.daily, changed = _gated_daily(ctx, state)
        else:
            result.daily = _preview_daily(ctx, state)

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
    elif parts:
        result.status = parts[0].status
    return result


# --- lab channel: the solve gate --------------------------------------------------------


def _gated_daily(ctx: RunContext, st: _State) -> tuple[PartResult, bool]:
    """One morning decision for the lab channel. Returns the result and whether ``posted``
    changed; on any Slack failure nothing changes, so tomorrow decides again (FR-024)."""
    if not ctx.force and posted_mod.posted_on(st.posted, st.today):
        return PartResult(RunStatus.ALREADY_POSTED), False
    token = ctx.env[BOT_TOKEN]
    current = posted_mod.open_post(st.posted)
    resolved: DailyPost | None = None
    if current is not None:
        try:
            bot_id = auth_test(token, **_slack(ctx))
            reactions = get_reactions(token, current.channel, current.ts, **_slack(ctx))
        except SlackMessageGone:
            return _repost(ctx, st, current)
        except SlackApiError as exc:
            return _failed(current, exc), False
        if gate.judge(reactions, ctx.env[LEARNER], bot_id) == "unsolved":
            return _remind(ctx, st, current)
        resolved = current

    choice = plan_today(st.catalog, st.progress, st.posted, st.today)
    if choice is None:
        return PartResult(
            RunStatus.NO_SCENARIO, error="게시할 수 있는 학습 항목이 없어요(카탈로그·계획 확인)"
        ), False
    payload = build_daily(choice, st.catalog, st.progress, st.today)
    try:
        channel, ts = post_message(token, ctx.env[LAB_CHANNEL], payload, **_slack(ctx))
    except SlackApiError as exc:
        return _failed(current, exc, choice), False
    if resolved is not None:
        _replace(st.posted, resolved, outcome="solved", resolved_at=ctx.now)
    st.posted.daily.append(
        DailyPost(
            date_kst=st.today,
            kind=choice.kind,
            day=choice.day,
            main_kind=choice.main_kind,
            main_id=choice.main_id,
            second_id=choice.second_id,
            posted_at=ctx.now,
            channel=channel,
            ts=ts,
            outcome="open",
        )
    )
    return PartResult(
        RunStatus.POSTED,
        kind=choice.kind,
        day=choice.day,
        main_id=choice.main_id,
        second_id=choice.second_id,
        resolved_id=resolved.main_id if resolved else None,
    ), True


def _remind(ctx: RunContext, st: _State, current: DailyPost) -> tuple[PartResult, bool]:
    if not gate.reminder_due(current, st.today):
        return _part(RunStatus.ALREADY_REMINDED, current), False
    payload, hinted = _reminder_payload(st, current, test_mode=False)
    try:
        post_message(
            ctx.env[BOT_TOKEN], current.channel, payload, thread_ts=current.ts, **_slack(ctx)
        )
    except SlackApiError as exc:
        return _failed(current, exc), False
    _replace(st.posted, current, reminders=[*current.reminders, st.today])
    return _part(RunStatus.REMINDED, current, hint_included=hinted), True


def _repost(ctx: RunContext, st: _State, current: DailyPost) -> tuple[PartResult, bool]:
    """The open problem's message is gone: post the same problem again and move the record
    to the new message. Never advance, since nobody can have marked it solved (research R9)."""
    payload = build_daily(_pick_of(current, st), st.catalog, st.progress, st.today, reposted=True)
    try:
        channel, ts = post_message(ctx.env[BOT_TOKEN], ctx.env[LAB_CHANNEL], payload, **_slack(ctx))
    except SlackApiError as exc:
        return _failed(current, exc), False
    _replace(st.posted, current, channel=channel, ts=ts, reposted_at=ctx.now)
    _notify(
        ctx,
        warning_payload(
            AGENT,
            [f"열린 문제({current.main_id})의 메시지를 찾을 수 없어 다시 게시했어요"],
            context_parts=_context(ctx),
            env=ctx.env,
            note="같은 문제를 유지",
        ),
    )
    return _part(RunStatus.REPOSTED, current), True


def _reminder_payload(
    st: _State, current: DailyPost, *, test_mode: bool
) -> tuple[dict[str, Any], bool]:
    hint = None
    if gate.hint_due(current, st.today) and (sid := gate.hint_source(current, st.catalog)):
        hint = st.catalog.hints[sid][0]
    item = st.catalog.get(current.main_id)
    title = item.title if item else current.main_id
    days = gate.days_open(current, st.today)
    return build_reminder(title, days, hint=hint, test_mode=test_mode), hint is not None


def _pick_of(post: DailyPost, st: _State) -> DayPick:
    """Rebuild the plan item of a recorded post, to post its message again."""
    plan = st.catalog.plan
    plan_day = plan.get(post.day) if plan is not None and post.day else None
    extras = plan.extras if plan is not None else []
    return DayPick(
        kind=post.kind if post.kind != "catchup" else "review",
        main_id=post.main_id,
        main_kind=post.main_kind,
        day=post.day,
        plan_day=plan_day,
        second_id=post.second_id,
        minutes=st.catalog.minutes_with_warmups(post.main_id, prog.done_missions(st.progress)),
        extra_index=extras.index(post.main_id) + 1 if post.main_id in extras else None,
        composite=plan_day is not None and plan_day.pool is not None,
    )


def _replace(posted: Posted, old: DailyPost, **update: Any) -> None:
    posted.daily[posted.daily.index(old)] = old.model_copy(update=update)


def _part(status: RunStatus, post: DailyPost, **kw: Any) -> PartResult:
    return PartResult(
        status,
        kind=post.kind,
        day=post.day,
        main_id=post.main_id,
        second_id=post.second_id,
        **kw,
    )


def _failed(
    current: DailyPost | None, exc: SlackApiError, choice: DayPick | None = None
) -> PartResult:
    if choice is not None:
        return PartResult(
            RunStatus.POST_FAILED,
            kind=choice.kind,
            day=choice.day,
            main_id=choice.main_id,
            second_id=choice.second_id,
            error=str(exc),
        )
    if current is not None:
        return _part(RunStatus.POST_FAILED, current, error=str(exc))
    return PartResult(RunStatus.POST_FAILED, error=str(exc))


def _slack(ctx: RunContext) -> dict[str, Any]:
    return {"client": ctx.http, "base_delay": ctx.base_delay}


# --- test channel / dry run: preview only -----------------------------------------------


def _preview_daily(ctx: RunContext, st: _State) -> PartResult:
    """What the lab channel would get today, without reading reactions or recording."""
    current = posted_mod.open_post(st.posted)
    test_mode = ctx.target == "test"
    if current is not None:
        payload, hinted = _reminder_payload(st, current, test_mode=test_mode)
        error = _deliver(ctx, payload)
        if error:
            return _part(RunStatus.POST_FAILED, current, error=error)
        return _part(RunStatus.REMINDED, current, hint_included=hinted)
    if not ctx.force and posted_mod.posted_on(st.posted, st.today):
        return PartResult(RunStatus.ALREADY_POSTED)
    choice = plan_today(st.catalog, st.progress, st.posted, st.today)
    if choice is None:
        return PartResult(
            RunStatus.NO_SCENARIO, error="게시할 수 있는 학습 항목이 없어요(카탈로그·계획 확인)"
        )
    error = _deliver(
        ctx, build_daily(choice, st.catalog, st.progress, st.today, test_mode=test_mode)
    )
    return PartResult(
        RunStatus.POST_FAILED if error else RunStatus.POSTED,
        kind=choice.kind,
        day=choice.day,
        main_id=choice.main_id,
        second_id=choice.second_id,
        error=error,
    )


# --- delivery ---------------------------------------------------------------------------


def _deliver(ctx: RunContext, payload: dict[str, Any]) -> str | None:
    """Send (or print in dry-run): the lab channel through the bot, the test channel through
    its webhook. Returns an error string on failure."""
    if ctx.dry_run:
        _print(ctx, payload)
        return None
    try:
        if ctx.target == "lab":
            post_message(ctx.env[BOT_TOKEN], ctx.env[LAB_CHANNEL], payload, **_slack(ctx))
        else:
            send_webhook(ctx.env[TEST_WEBHOOK], payload, client=ctx.http, base_delay=ctx.base_delay)
    except (SlackSendError, SlackApiError) as exc:
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
