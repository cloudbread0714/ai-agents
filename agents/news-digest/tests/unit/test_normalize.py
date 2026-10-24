from datetime import UTC, datetime, timedelta

import pytest

from news_digest.models import Article
from news_digest.normalize import article_id, dedupe, limit_candidates, normalize_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "https://aws.amazon.com/blogs/aws/eks-1-34/?utm_source=rss&utm_medium=rss",
            "https://aws.amazon.com/blogs/aws/eks-1-34",
        ),
        (
            "http://www.Example.dev/posts/mcp-servers#comments",
            "https://example.dev/posts/mcp-servers",
        ),
        ("https://example.com/a/?b=2&a=1&ref=hn", "https://example.com/a?a=1&b=2"),
        ("https://example.com/item?id=5&source=rss&fbclid=x", "https://example.com/item?id=5"),
        ("https://example.com/", "https://example.com"),
        ("https://example.com:8443/Path/Case", "https://example.com:8443/Path/Case"),
    ],
)
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


def test_same_article_from_hn_and_aws_blog_has_same_id():
    hn = "https://aws.amazon.com/blogs/aws/amazon-eks-kubernetes-1-34/"
    blog = (
        "https://aws.amazon.com/blogs/aws/amazon-eks-kubernetes-1-34/?utm_source=rss&utm_medium=rss"
    )
    assert article_id(hn) == article_id(blog)
    assert len(article_id(hn)) == 16


def _article(url: str, source: str, hours_ago: int) -> Article:
    return Article(
        id=article_id(url),
        title=url,
        url=url,
        normalized_url=normalize_url(url),
        source=source,
        category_hint="infra",
        published_at=datetime(2026, 10, 25, tzinfo=UTC) - timedelta(hours=hours_ago),
    )


def test_dedupe_keeps_first_in_source_order():
    a = _article("https://x.com/a?utm_source=1", "first", 5)
    b = _article("https://x.com/a", "second", 1)
    c = _article("https://x.com/c", "second", 2)
    assert [x.source for x in dedupe([a, b, c])] == ["first", "second"]
    assert dedupe([a, b, c])[1] is c


def test_limit_candidates_keeps_newest():
    articles = [_article(f"https://x.com/{i}", "s", hours_ago=i) for i in range(10)]
    limited = limit_candidates(articles, 3)
    assert [a.url for a in limited] == ["https://x.com/0", "https://x.com/1", "https://x.com/2"]
