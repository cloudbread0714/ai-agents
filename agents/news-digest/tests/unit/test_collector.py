from datetime import timedelta

import httpx

from nd_support import FEED_URLS, fixture_bytes
from news_digest.collector import collect, parse_feed
from news_digest.models import Source

SRC = Source(name="AWS News Blog", url=FEED_URLS["aws_blog.xml"], category="infra")


def test_parse_rss_items(settings, now):
    articles = parse_feed(fixture_bytes("aws_blog.xml"), SRC, settings, now)
    titles = [a.title for a in articles]
    assert titles == [
        "Amazon EKS adds native support for Kubernetes 1.34 with in-place pod resize",
        "Announcing CloudWatch Application Signals for Lambda",
    ]
    eks = articles[0]
    assert eks.url.startswith("https://aws.amazon.com/blogs/aws/amazon-eks-kubernetes-1-34/")
    assert eks.normalized_url == "https://aws.amazon.com/blogs/aws/amazon-eks-kubernetes-1-34"
    assert eks.excerpt.startswith("Amazon EKS now supports Kubernetes 1.34, including")
    assert "<" not in eks.excerpt
    assert eks.category_hint == "infra"
    assert eks.source == "AWS News Blog"


def test_stale_items_filtered_by_freshness(settings, now):
    articles = parse_feed(fixture_bytes("aws_blog.xml"), SRC, settings, now)
    cutoff = now - timedelta(hours=settings.selection.freshness_hours)
    assert all(a.published_at >= cutoff for a in articles)
    assert not any("old-post" in a.url for a in articles)


def test_missing_date_uses_collection_time(settings, now):
    src = Source(name="AWS What's New", url=FEED_URLS["aws_whats_new.xml"], category="infra")
    articles = parse_feed(fixture_bytes("aws_whats_new.xml"), src, settings, now)
    undated = next(a for a in articles if a.url.endswith("/no-date/"))
    assert undated.published_inferred is True
    assert undated.published_at == now


def test_atom_html_summary_is_cleaned(settings, now):
    src = Source(name="Agents", url=FEED_URLS["atom_blog.xml"], category="ai_agent")
    [article] = parse_feed(fixture_bytes("atom_blog.xml"), src, settings, now)
    assert article.excerpt == (
        "How we made our agent framework recover from tool failures & measure it with evals."
    )


def test_title_and_excerpt_truncated_to_300(settings, now):
    long = "x" * 1000
    feed = f"""<?xml version="1.0"?><rss version="2.0"><channel><item>
      <title>{long}</title><link>https://a.example/p</link>
      <pubDate>Sat, 25 Oct 2026 20:00:00 +0000</pubDate><description>{long}</description>
    </item></channel></rss>""".encode()
    [article] = parse_feed(feed, SRC, settings, now)
    assert len(article.title) == 300
    assert len(article.excerpt) == 300


def test_max_items_per_source_keeps_newest(settings, now):
    src = SRC.model_copy(update={"max_items": 1})
    articles = parse_feed(fixture_bytes("aws_blog.xml"), src, settings, now)
    assert [a.title[:10] for a in articles] == ["Amazon EKS"]


def test_collect_reports_per_source_results(httpx_mock, settings, now, sources):
    httpx_mock.add_response(url=FEED_URLS["aws_blog.xml"], content=fixture_bytes("aws_blog.xml"))
    httpx_mock.add_response(url=FEED_URLS["aws_whats_new.xml"], content=fixture_bytes("broken.xml"))
    httpx_mock.add_response(url=FEED_URLS["hnrss.xml"], status_code=404)
    httpx_mock.add_exception(
        httpx.ConnectTimeout("timeout"), url=FEED_URLS["atom_blog.xml"], is_reusable=True
    )

    with httpx.Client() as http:
        articles, results = collect(sources.enabled, settings, now, http, base_delay=0)

    by_source = {r.source: r for r in results}
    assert by_source["AWS News Blog"].ok and by_source["AWS News Blog"].item_count == 2
    assert not by_source["AWS What's New"].ok
    assert "HTTP 404" in by_source["Hacker News"].error
    assert "ConnectTimeout" in by_source["Agents Blog"].error
    assert {a.source for a in articles} == {"AWS News Blog"}
    # transport errors are retried 3 times; 404 is not retried
    assert len(httpx_mock.get_requests(url=FEED_URLS["atom_blog.xml"])) == 3
    assert len(httpx_mock.get_requests(url=FEED_URLS["hnrss.xml"])) == 1


def test_collect_preserves_source_order(mock_feeds, settings, now, sources):
    mock_feeds()
    with httpx.Client() as http:
        articles, results = collect(sources.enabled, settings, now, http, base_delay=0)
    assert all(r.ok for r in results)
    order = [s.name for s in sources.enabled]
    positions = [order.index(a.source) for a in articles]
    assert positions == sorted(positions)
