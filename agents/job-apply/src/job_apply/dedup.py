"""Duplicate keys for postings and lookup of done folders (research R10, FR-016)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from job_apply.folders import iter_folders

TRACKING = {"ref", "fbclid", "gclid"}


def url_key(url: str) -> str:
    parts = urlsplit(url.strip())
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING
    )
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def text_key(text: str) -> str:
    return "text:" + hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def key_for(url: str | None, text: str) -> str:
    return url_key(url) if url else text_key(text)


def find_done(applications: Path, key: str) -> Path | None:
    """The done folder for ``key``; failed and in-progress folders do not count."""
    for folder, meta in iter_folders(applications):
        if meta.status == "done" and meta.posting.url_key == key:
            return folder
    return None
