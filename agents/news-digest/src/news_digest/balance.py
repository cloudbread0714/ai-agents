"""Topic balance between infra and AI-agent posts (FR-007, research R6)."""

from __future__ import annotations

from news_digest.models import Category

_OTHER: dict[str, Category] = {"infra": "ai_agent", "ai_agent": "infra"}


def preferred_category(recent: list[Category], window: int) -> Category | None:
    """The opposite category when the last ``window`` posts all share one; otherwise None."""
    last = recent[-window:]
    if len(last) < window or len(set(last)) != 1:
        return None
    return _OTHER[last[0]]
