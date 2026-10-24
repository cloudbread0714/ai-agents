import pytest

from shared.llm import Price, cost_usd

PRICING = {
    "claude-opus-5-5": Price(input=4.0, output=20.0),
    "claude-haiku-5-5": Price(input=0.10, output=0.50),
}


def test_cost_per_million_tokens():
    assert cost_usd(1_000_000, 0, "claude-opus-5-5", PRICING) == pytest.approx(4.0)
    assert cost_usd(10_000, 2_000, "claude-opus-5-5", PRICING) == pytest.approx(0.04 + 0.04)


def test_unknown_model_raises():
    with pytest.raises(KeyError, match="claude-unknown"):
        cost_usd(1, 1, "claude-unknown", PRICING)
