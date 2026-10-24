"""RSS/Atom collection (research R4)."""

from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import feedparser
import httpx

from news_digest.models import Article, Settings, Source, SourceResult
from news_digest.normalize import article_id, normalize_url
from shared.logging import get_logger
from shared.retry import retryable

log = get_logger(__name__)

USER_AGENT = "news-digest/0.1 (RSS reader; +https://github.com/)"
FETCH_TIMEOUT = 15.0
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?])")


class FeedError(Exception):
    pass


class _RetryableFeedError(FeedError):
    pass


def _clean(text: str, limit: int) -> str:
    text = html.unescape(_TAG_RE.sub(" ", text or ""))
    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", _WS_RE.sub(" ", text))
    return text.strip()[:limit]


def _entry_time(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime(*parsed[:6], tzinfo=UTC) if parsed else None


def parse_feed(content: bytes, source: Source, settings: Settings, now: datetime) -> list[Article]:
    feed = feedparser.parse(content)
    if feed.bozo and not feed.entries:
        raise FeedError(f"unparseable feed: {type(feed.bozo_exception).__name__}")

    cutoff = now - timedelta(hours=settings.selection.freshness_hours)
    articles = []
    for entry in feed.entries:
        link = entry.get("link")
        title = _clean(entry.get("title", ""), 300)
        if not link or not title:
            continue
        published = _entry_time(entry)
        if published is not None and published < cutoff:
            continue
        articles.append(
            Article(
                id=article_id(link),
                title=title,
                url=link,
                normalized_url=normalize_url(link),
                source=source.name,
                category_hint=source.category,
                published_at=published or now,
                published_inferred=published is None,
                excerpt=_clean(entry.get("summary", ""), 300),
            )
        )
    articles.sort(key=lambda a: a.published_at, reverse=True)
    return articles[: source.max_items or settings.selection.max_items_per_source]


def _fetch(http: httpx.Client, source: Source, base_delay: float) -> bytes:
    @retryable(retry_on=(_RetryableFeedError,), base_delay=base_delay, target=f"feed:{source.name}")
    def get() -> bytes:
        try:
            resp = http.get(
                source.url,
                timeout=FETCH_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
        except httpx.TransportError as exc:
            raise _RetryableFeedError(f"{type(exc).__name__}") from None
        if resp.status_code == 429 or resp.status_code >= 500:
            raise _RetryableFeedError(f"HTTP {resp.status_code}")
        if not resp.is_success:
            raise FeedError(f"HTTP {resp.status_code}")
        return resp.content

    return get()


def _collect_one(
    source: Source, settings: Settings, now: datetime, http: httpx.Client, base_delay: float
) -> tuple[list[Article], SourceResult]:
    try:
        articles = parse_feed(_fetch(http, source, base_delay), source, settings, now)
    except FeedError as exc:
        log.warning("feed_failed", extra={"fields": {"source": source.name, "error": str(exc)}})
        return [], SourceResult(source=source.name, ok=False, error=str(exc))
    log.info("feed_collected", extra={"fields": {"source": source.name, "items": len(articles)}})
    return articles, SourceResult(source=source.name, ok=True, item_count=len(articles))


def collect(
    sources: list[Source],
    settings: Settings,
    now: datetime,
    http: httpx.Client,
    *,
    base_delay: float = 1.0,
) -> tuple[list[Article], list[SourceResult]]:
    """Fetch all sources in parallel. Articles keep source list order, newest first per source."""
    with ThreadPoolExecutor(max_workers=min(8, len(sources) or 1)) as pool:
        results = list(
            pool.map(lambda s: _collect_one(s, settings, now, http, base_delay), sources)
        )
    articles = [a for batch, _ in results for a in batch]
    return articles, [r for _, r in results]
