"""Anthropic client factory and token cost calculation."""

from __future__ import annotations

from collections.abc import Mapping

import anthropic
from pydantic import BaseModel, Field


class Price(BaseModel):
    """USD per 1M tokens."""

    input: float = Field(ge=0)
    output: float = Field(ge=0)


def make_client(max_retries: int = 3, api_key: str | None = None) -> anthropic.Anthropic:
    # The SDK retries 408/409/429/5xx and connection errors with exponential backoff.
    return anthropic.Anthropic(api_key=api_key, max_retries=max_retries)


def cost_usd(
    input_tokens: int, output_tokens: int, model: str, pricing: Mapping[str, Price]
) -> float:
    if model not in pricing:
        raise KeyError(f"no pricing configured for model {model}")
    price = pricing[model]
    return (input_tokens * price.input + output_tokens * price.output) / 1_000_000
