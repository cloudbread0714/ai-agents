"""Slack Incoming Webhook sender."""

from __future__ import annotations

import re
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
