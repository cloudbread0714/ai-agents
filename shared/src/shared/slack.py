"""Slack senders: Incoming Webhooks and the bot-token Web API."""

from __future__ import annotations

import re
import time
from typing import Any

import httpx

from shared.logging import get_logger
from shared.retry import retryable

log = get_logger(__name__)
# httpx logs every request URL at INFO; the webhook URL is the secret itself.
get_logger("httpx")

_WEBHOOK_RE = re.compile(r"(https://hooks\.slack\.com/services/).*")


class SlackSendError(Exception):
    """Webhook delivery failed. Messages never include the webhook URL."""


class _RetryableSlackError(SlackSendError):
    pass


def mask_webhook(url: str) -> str:
    return _WEBHOOK_RE.sub(r"\1***", url)


def escape_mrkdwn(text: str) -> str:
    """Escape the three characters Slack mrkdwn treats as control characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def slack_link(url: str, label: str) -> str:
    safe_url = url.replace("|", "%7C").replace(">", "%3E").replace("<", "%3C")
    return f"<{safe_url}|{escape_mrkdwn(label)}>"


def send_webhook(
    url: str,
    payload: dict[str, Any],
    *,
    client: httpx.Client | None = None,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    timeout: float = 10.0,
) -> None:
    """POST ``payload`` to an Incoming Webhook; succeed only on 2xx with body ``ok``.

    429, 5xx and network errors are retried; other failures raise immediately.
    """
    http = client or httpx.Client()

    @retryable(
        retry_on=(_RetryableSlackError,),
        max_attempts=max_attempts,
        base_delay=base_delay,
        target=f"slack:{mask_webhook(url)}",
    )
    def _send() -> None:
        try:
            resp = http.post(url, json=payload, timeout=timeout)
        except httpx.TransportError as exc:
            raise _RetryableSlackError(f"network error: {type(exc).__name__}") from None
        if resp.status_code == 429 or resp.status_code >= 500:
            raise _RetryableSlackError(f"HTTP {resp.status_code}")
        if not resp.is_success or resp.text.strip() != "ok":
            raise SlackSendError(f"HTTP {resp.status_code}: {resp.text[:100]}")

    try:
        _send()
    finally:
        if client is None:
            http.close()
    log.info("slack_sent", extra={"fields": {"webhook": mask_webhook(url)}})


# --- Web API with a bot token ----------------------------------------------------------

API_BASE = "https://slack.com/api/"
# Errors that a retry can fix; every other ``ok: false`` code fails at once.
_RETRYABLE_CODES = {"ratelimited", "internal_error", "fatal_error", "service_unavailable"}
_MAX_RETRY_AFTER = 10.0
# Callers treat these as outcomes, not failures.
_BENIGN_CODES = {"already_reacted"}


class SlackApiError(Exception):
    """A Web API call failed. Messages carry the method and Slack's error code, never the token."""

    def __init__(self, method: str, code: str):
        super().__init__(f"{method}: {code}")
        self.method = method
        self.code = code


class SlackMessageGone(SlackApiError):
    """The message the call referred to no longer exists (``message_not_found``)."""


class _RetryableApiError(SlackApiError):
    def __init__(self, method: str, code: str, retry_after: float = 0.0):
        super().__init__(method, code)
        self.retry_after = retry_after


def _call(
    token: str,
    method: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
    client: httpx.Client | None = None,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Call ``method`` and return the response body. 429, 5xx, network errors and the
    retryable error codes are retried; ``Retry-After`` is honoured up to 10 seconds."""
    http = client or httpx.Client()
    headers = {"Authorization": f"Bearer {token}"}

    @retryable(
        retry_on=(_RetryableApiError,),
        max_attempts=max_attempts,
        base_delay=base_delay,
        target=f"slack-api:{method}",
    )
    def _send() -> dict[str, Any]:
        try:
            if json is None:
                resp = http.get(API_BASE + method, params=params, headers=headers, timeout=timeout)
            else:
                resp = http.post(API_BASE + method, json=json, headers=headers, timeout=timeout)
        except httpx.TransportError as exc:
            raise _RetryableApiError(method, f"network error: {type(exc).__name__}") from None
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = min(float(resp.headers.get("Retry-After", 0) or 0), _MAX_RETRY_AFTER)
            if wait and base_delay:
                time.sleep(wait)
            raise _RetryableApiError(method, f"HTTP {resp.status_code}")
        try:
            body = resp.json()
        except ValueError:
            raise SlackApiError(method, f"HTTP {resp.status_code}: not JSON") from None
        if not body.get("ok"):
            code = str(body.get("error", "unknown_error"))
            if code in _RETRYABLE_CODES:
                raise _RetryableApiError(method, code)
            if code == "message_not_found":
                raise SlackMessageGone(method, code)
            raise SlackApiError(method, code)
        return body

    try:
        return _send()
    except _RetryableApiError as exc:
        log.error(
            "slack_api_failed",
            extra={"fields": {"method": method, "attempts": max_attempts, "error": exc.code}},
        )
        raise SlackApiError(method, exc.code) from None
    except SlackApiError as exc:
        if exc.code not in _BENIGN_CODES:
            log.error(
                "slack_api_failed",
                extra={"fields": {"method": method, "attempts": 1, "error": exc.code}},
            )
        raise
    finally:
        if client is None:
            http.close()


def auth_test(token: str, **kw: Any) -> str:
    """The bot's own user ID."""
    return str(_call(token, "auth.test", json={}, **kw)["user_id"])


def post_message(
    token: str, channel: str, payload: dict[str, Any], *, thread_ts: str | None = None, **kw: Any
) -> tuple[str, str]:
    """Post ``payload`` (``{"text", "blocks"}``) and return ``(channel, ts)`` of the new message."""
    body = {"channel": channel, **payload}
    if thread_ts:
        body["thread_ts"] = thread_ts
    resp = _call(token, "chat.postMessage", json=body, **kw)
    return str(resp["channel"]), str(resp["ts"])


def get_reactions(token: str, channel: str, ts: str, **kw: Any) -> dict[str, set[str]]:
    """Reaction name → IDs of the users who added it (``{}`` when there are none)."""
    resp = _call(
        token,
        "reactions.get",
        params={"channel": channel, "timestamp": ts, "full": "true"},
        **kw,
    )
    reactions = resp.get("message", {}).get("reactions", [])
    return {r["name"]: set(r.get("users", [])) for r in reactions}


def add_reaction(token: str, channel: str, ts: str, name: str, **kw: Any) -> bool:
    """Add ``name`` to the message. False (not an error) when it is already there."""
    try:
        _call(
            token, "reactions.add", json={"channel": channel, "timestamp": ts, "name": name}, **kw
        )
    except SlackApiError as exc:
        if exc.code == "already_reacted":
            return False
        raise
    return True
