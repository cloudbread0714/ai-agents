import pytest

from news_digest.balance import preferred_category


@pytest.mark.parametrize(
    ("recent", "window", "expected"),
    [
        (["infra", "infra"], 2, "ai_agent"),
        (["ai_agent", "ai_agent"], 2, "infra"),
        (["ai_agent", "infra", "infra"], 2, "ai_agent"),
        (["infra", "ai_agent"], 2, None),
        (["infra"], 2, None),
        ([], 2, None),
        (["infra", "infra", "infra"], 3, "ai_agent"),
        (["ai_agent", "infra", "infra"], 3, None),
    ],
)
def test_preferred_category(recent, window, expected):
    assert preferred_category(recent, window) == expected
