"""Test-channel error and warning messages (contracts/slack-message.md)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from zoneinfo import ZoneInfo

from news_digest.formatter import escape_mrkdwn
from news_digest.models import RunResult
from shared.logging import mask_secrets


def run_url(env: Mapping[str, str]) -> str | None:
    keys = ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID")
    if not all(env.get(k) for k in keys):
        return None
    return (
        f"{env['GITHUB_SERVER_URL']}/{env['GITHUB_REPOSITORY']}/actions/runs/{env['GITHUB_RUN_ID']}"
    )


def _context(result: RunResult, tz: str, env: Mapping[str, str]) -> dict[str, Any]:
    at = result.run_at.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M KST")
    parts = [f"실행: {at}", f"후보 {result.candidate_count}건"]
    if failed := result.failed_sources:
        parts.append(f"실패 소스: {escape_mrkdwn(', '.join(failed))}")
    if url := run_url(env):
        parts.append(f"<{url}|GitHub Actions 실행 로그>")
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": " · ".join(parts)}]}


def build_alert_payload(result: RunResult, *, tz: str, env: Mapping[str, str]) -> dict[str, Any]:
    status = result.status.value if result.status else "UNEXPECTED_ERROR"
    cause = escape_mrkdwn(mask_secrets(result.error or "unknown"))
    return {
        "text": f"⚠️ news-digest {status}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*⚠️ news-digest: {status}*\n"
                    f"단계: {result.stage or 'unknown'}\n원인: {cause}",
                },
            },
            _context(result, tz, env),
        ],
    }


def build_warning_payload(result: RunResult, *, tz: str, env: Mapping[str, str]) -> dict[str, Any]:
    lines = "\n".join(f"• {escape_mrkdwn(mask_secrets(w))}" for w in result.warnings)
    return {
        "text": "⚠️ news-digest WARNING",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*⚠️ news-digest: WARNING* (게시는 완료됨)\n{lines}",
                },
            },
            _context(result, tz, env),
        ],
    }
