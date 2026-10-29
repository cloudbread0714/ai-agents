"""Automatic ✅ on today's problem when ``/lab-check`` finishes it (004 research R8).

Slack is an add-on here: learning commands work offline, so every outcome, including a
missing token or a failed call, comes back as a status and a line for the learner, never
as an exception. The open problem is read from the local ``data/posted.json``, which the
morning run commits; a stale checkout simply finds nothing to mark.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

from shared.logging import get_logger
from shared.slack import SlackApiError, add_reaction
from troubleshoot_lab import posted as posted_mod
from troubleshoot_lab import progress as prog
from troubleshoot_lab.catalog import Catalog
from troubleshoot_lab.models import Progress

log = get_logger(__name__)

BOT_TOKEN = "SLACK_BOT_TOKEN"
CHECK_MARK = "white_check_mark"
MANUAL = "Slack에서 직접 달아 주세요."

ReactionStatus = Literal["added", "already", "partial", "not_open", "no_config", "failed"]


@dataclass(frozen=True)
class ReactionResult:
    status: ReactionStatus
    message: str | None = None


class Reactor:
    def __init__(
        self,
        lab_root: Path,
        env: Mapping[str, str],
        *,
        http_factory: Callable[[], httpx.Client] = httpx.Client,
        base_delay: float = 1.0,
    ):
        self.posted_path = lab_root / "data" / "posted.json"
        self.env = env
        self.http_factory = http_factory
        self.base_delay = base_delay

    def after_done(self, item_id: str, progress: Progress, catalog: Catalog) -> ReactionResult:
        """Called right after ``item_id`` was solved or completed."""
        try:
            current = posted_mod.open_post(posted_mod.load(self.posted_path))
        except Exception as exc:  # noqa: BLE001 - a broken record must not fail the check
            log.warning("posted_unreadable", extra={"fields": {"error": type(exc).__name__}})
            return ReactionResult(
                "failed", f"✅ 자동 반응을 달지 못했어요(게시 기록 오류). {MANUAL}"
            )
        if current is None:
            return ReactionResult(
                "not_open",
                "최신 게시 기록이 없어요. "
                "git pull 뒤 다시 확인하거나 Slack에서 직접 ✅를 달아 주세요.",
            )
        items = [i for i in (current.main_id, current.second_id) if i]
        if item_id not in items:
            return ReactionResult("not_open")
        remaining = [i for i in items if not _done(i, progress, catalog)]
        if remaining:
            titles = ", ".join(_title(i, catalog) for i in remaining)
            return ReactionResult(
                "partial",
                f"오늘의 문제에 남은 항목이 있어요: {titles}. 다 끝내면 ✅를 달아 줄게요.",
            )
        token = self.env.get(BOT_TOKEN)
        if not token:
            return ReactionResult(
                "no_config", f"Slack 값(SLACK_BOT_TOKEN 등)이 없어 ✅를 달지 못했어요. {MANUAL}"
            )
        try:
            with self.http_factory() as http:
                added = add_reaction(
                    token,
                    current.channel,
                    current.ts,
                    CHECK_MARK,
                    client=http,
                    base_delay=self.base_delay,
                )
        except SlackApiError as exc:
            return ReactionResult("failed", f"✅ 자동 반응을 달지 못했어요({exc.code}). {MANUAL}")
        if not added:
            return ReactionResult("already", "Slack 오늘의 문제에 이미 ✅가 있어요.")
        return ReactionResult(
            "added", "Slack 오늘의 문제에 ✅를 달았어요. 내일 아침에 다음 문제가 올라와요."
        )


def _done(item_id: str, progress: Progress, catalog: Catalog) -> bool:
    if catalog.kind(item_id) == "mission":
        return item_id in prog.done_missions(progress)
    return prog.scenario_status(progress, item_id) == "solved"


def _title(item_id: str, catalog: Catalog) -> str:
    item = catalog.get(item_id)
    return item.title if item else item_id
