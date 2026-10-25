"""Test-channel failure and warning payloads shared by every agent.

Causes, warnings and context parts are plain text: the helpers mask secrets and
escape mrkdwn, so callers never pass pre-escaped strings.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from shared.logging import mask_secrets
from shared.slack import escape_mrkdwn, slack_link


def run_url(env: Mapping[str, str]) -> str | None:
    keys = ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID")
    if not all(env.get(k) for k in keys):
        return None
    return (
        f"{env['GITHUB_SERVER_URL']}/{env['GITHUB_REPOSITORY']}/actions/runs/{env['GITHUB_RUN_ID']}"
    )


def _clean(text: str) -> str:
    return escape_mrkdwn(mask_secrets(text))


def _context(parts: Sequence[str], env: Mapping[str, str]) -> dict[str, Any]:
    items = [_clean(p) for p in parts]
    if url := run_url(env):
        items.append(slack_link(url, "GitHub Actions 실행 로그"))
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": " · ".join(items)}]}


def _section(text: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def alert_payload(
    agent: str,
    status: str,
    *,
    stage: str | None,
    cause: str | None,
    context_parts: Sequence[str],
    env: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "text": f"⚠️ {agent} {status}",
        "blocks": [
            _section(
                f"*⚠️ {agent}: {status}*\n단계: {_clean(stage or 'unknown')}\n"
                f"원인: {_clean(cause or 'unknown')}"
            ),
            _context(context_parts, env),
        ],
    }


def warning_payload(
    agent: str,
    warnings: Sequence[str],
    *,
    context_parts: Sequence[str],
    env: Mapping[str, str],
    note: str = "게시는 완료됨",
) -> dict[str, Any]:
    lines = "\n".join(f"• {_clean(w)}" for w in warnings)
    return {
        "text": f"⚠️ {agent} WARNING",
        "blocks": [
            _section(f"*⚠️ {agent}: WARNING* ({note})\n{lines}"),
            _context(context_parts, env),
        ],
    }
