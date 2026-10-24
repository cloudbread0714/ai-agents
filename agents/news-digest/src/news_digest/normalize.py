"""URL normalization and candidate de-duplication (research R5)."""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from news_digest.models import Article

_TRACKING_PARAMS = {"ref", "source", "fbclid", "gclid", "mc_cid", "mc_eid"}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    netloc = f"{host}:{parts.port}" if parts.port else host
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
    )
    return urlunsplit(("https", netloc, parts.path.rstrip("/"), urlencode(query), ""))


def article_id(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()[:16]


def dedupe(articles: list[Article]) -> list[Article]:
    """Keep the first occurrence of each article id (source list order wins)."""
    seen: set[str] = set()
    unique = []
    for article in articles:
        if article.id not in seen:
            seen.add(article.id)
            unique.append(article)
    return unique


def limit_candidates(articles: list[Article], max_candidates: int) -> list[Article]:
    """Newest first, capped at ``max_candidates``."""
    return sorted(articles, key=lambda a: a.published_at, reverse=True)[:max_candidates]
