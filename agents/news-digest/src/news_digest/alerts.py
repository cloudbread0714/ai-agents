"""Test-channel error and warning messages (contracts/slack-message.md).

Thin adapter over ``shared.alerts``: turns a ``RunResult`` into its arguments.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from zoneinfo import ZoneInfo

from news_digest.models import RunResult
from shared.alerts import alert_payload, run_url, warning_payload

__all__ = ["build_alert_payload", "build_warning_payload", "run_url"]

AGENT = "news-digest"


def _context_parts(result: RunResult, tz: str) -> list[str]:
    at = result.run_at.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M KST")
    parts = [f"실행: {at}", f"후보 {result.candidate_count}건"]
    if failed := result.failed_sources:
        parts.append(f"실패 소스: {', '.join(failed)}")
    return parts


def build_alert_payload(result: RunResult, *, tz: str, env: Mapping[str, str]) -> dict[str, Any]:
    return alert_payload(
        AGENT,
        result.status.value if result.status else "UNEXPECTED_ERROR",
        stage=result.stage,
        cause=result.error,
        context_parts=_context_parts(result, tz),
        env=env,
    )


def build_warning_payload(result: RunResult, *, tz: str, env: Mapping[str, str]) -> dict[str, Any]:
    return warning_payload(
        AGENT, result.warnings, context_parts=_context_parts(result, tz), env=env
    )
