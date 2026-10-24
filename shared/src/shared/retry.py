"""Common retry policy for external calls: exponential backoff with jitter, bounded attempts."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import tenacity

from shared.logging import get_logger

log = get_logger(__name__)

F = TypeVar("F", bound=Callable)


def retryable(
    *,
    retry_on: tuple[type[BaseException], ...],
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    target: str = "",
) -> Callable[[F], F]:
    """Retry the wrapped call on ``retry_on`` errors and re-raise the last one when exhausted."""

    def log_retry(state: tenacity.RetryCallState) -> None:
        exc = state.outcome.exception() if state.outcome else None
        log.warning(
            "retry",
            extra={
                "fields": {
                    "target": target,
                    "attempt": state.attempt_number,
                    "max_attempts": max_attempts,
                    "error": f"{type(exc).__name__}: {exc}" if exc else None,
                }
            },
        )

    return tenacity.retry(
        stop=tenacity.stop_after_attempt(max_attempts),
        wait=tenacity.wait_exponential_jitter(
            multiplier=base_delay, max=max_delay, jitter=base_delay
        ),
        retry=tenacity.retry_if_exception_type(retry_on),
        before_sleep=log_retry,
        reraise=True,
    )
