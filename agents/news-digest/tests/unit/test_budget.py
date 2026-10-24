from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from nd_support import FakeAnthropic, FakeResponse, candidate_ids, make_selection
from news_digest.models import Article, DigestSelection
from news_digest.normalize import article_id, normalize_url
from news_digest.selector import BudgetExceeded, select

CTX = dict(today_kst=date(2026, 10, 26), recent_categories=[], preferred=None)


def _articles(n: int) -> list[Article]:
    out = []
    for i in range(n):
        url = f"https://example.com/{i}"
        out.append(
            Article(
                id=article_id(url),
                title=f"t{i}",
                url=url,
                normalized_url=normalize_url(url),
                source="s",
                category_hint="infra",
                published_at=datetime(2026, 10, 25, tzinfo=UTC) - timedelta(hours=i),
            )
        )
    return out


def tokens_per_candidate(per: int, base: int = 1_000):
    return lambda kwargs: base + per * len(candidate_ids(kwargs))


def test_estimate_within_budget_sends_all(settings):
    # 40 candidates * 250 tokens + 1000 = 11k input -> 0.044 + 4000 * 20e-6 = 0.124 < 0.30
    cands = _articles(40)
    client = FakeAnthropic(
        responses=[FakeResponse(make_selection(cands[0].id))],
        count_tokens_fn=tokens_per_candidate(250),
    )
    outcome = select(client, settings, cands, **CTX)
    assert len(candidate_ids(client.parse_calls[0])) == 40
    assert outcome.estimated_cost_usd == pytest.approx(11_000 * 4e-6 + 4_000 * 20e-6)
    assert client.count_calls[0]["output_format"] is DigestSelection


def test_over_budget_trims_oldest_candidates(settings):
    # budget 0.30, output reserve 0.08 -> input must be <= 55k tokens
    cands = _articles(40)
    client = FakeAnthropic(
        responses=[FakeResponse(make_selection(cands[0].id))],
        count_tokens_fn=tokens_per_candidate(2_000),  # 40 -> 81k, 30 -> 61k, 23 -> 47k
    )
    select(client, settings, cands, **CTX)
    sent = candidate_ids(client.parse_calls[0])
    assert len(sent) == 23
    assert sent == [c.id for c in cands[:23]]  # newest kept
    assert len(client.count_calls) == 3


def test_still_over_budget_after_three_trims_does_not_call_llm(settings):
    cands = _articles(40)
    client = FakeAnthropic(count_tokens_fn=tokens_per_candidate(100_000))
    with pytest.raises(BudgetExceeded):
        select(client, settings, cands, **CTX)
    assert client.parse_calls == []
    assert len(client.count_calls) == 4  # initial + 3 trims


def test_retry_skipped_when_remaining_budget_too_small(settings):
    """A re-request after invalid output must fit in what is left of the budget (C1)."""
    cands = _articles(5)
    try:
        DigestSelection.model_validate({})
    except ValidationError as exc:
        invalid = exc
    # first call is billed (but returns invalid output): 0.20 spent of 0.30
    first = FakeResponse(None, input_tokens=25_000, output_tokens=5_000)
    client = FakeAnthropic(
        responses=[first, invalid], count_tokens_fn=lambda kwargs: 10_000
    )  # estimate 0.12 > remaining 0.10
    with pytest.raises(BudgetExceeded):
        select(client, settings, cands, **CTX)
    assert len(client.parse_calls) == 1
