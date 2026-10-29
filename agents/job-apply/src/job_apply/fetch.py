"""Fetching a posting page and deciding "could not fetch" (research R8, FR-017).

JSON-LD ``JobPosting`` and ``__NEXT_DATA__`` are tried before trafilatura. A failure is
not an exception: it comes back as ``FetchResult(status="failed", reason=...)`` so the
caller can ask the user for the body.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx
import trafilatura

from job_apply.config import FetchConfig
from shared.logging import get_logger
from shared.retry import retryable

log = get_logger(__name__)

LOGIN_SIGNALS = ("로그인", "login", "sign in", "access denied", "권한이 없", "회원가입")
_LD_RE = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S | re.I
)
_NEXT_RE = re.compile(r"<script[^>]*id=[\"']__NEXT_DATA__[\"'][^>]*>(.*?)</script>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_HANGUL = re.compile(r"[가-힣]")
_META_CHARSET = re.compile(rb"<meta[^>]+charset=[\"']?([\w-]+)", re.I)


@dataclass
class FetchResult:
    status: str  # ok | failed
    text: str = ""
    reason: str | None = None


class _Retry(Exception):
    pass


def _strip_html(text: str) -> str:
    text = re.sub(r"<\s*(br|/p|/li|/h\d)\s*/?>", "\n", text, flags=re.I)
    text = html_lib.unescape(_TAG_RE.sub("", text))
    return "\n".join(ln.strip() for ln in text.splitlines() if ln.strip())


def _job_postings(node: Any):
    if isinstance(node, list):
        for item in node:
            yield from _job_postings(item)
    elif isinstance(node, dict):
        kind = node.get("@type")
        if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
            yield node
        for key in ("@graph", "mainEntity"):
            if key in node:
                yield from _job_postings(node[key])


def from_json_ld(page: str) -> str | None:
    for raw in _LD_RE.findall(page):
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
        for job in _job_postings(data):
            org = job.get("hiringOrganization") or {}
            parts = [
                str(job.get("title") or ""),
                str(org.get("name") or "") if isinstance(org, dict) else str(org),
                f"마감: {job['validThrough']}" if job.get("validThrough") else "",
                _strip_html(str(job.get("description") or "")),
            ]
            text = "\n".join(p for p in parts if p)
            if text.strip():
                return text
    return None


def _strings(node: Any, out: list[str]) -> None:
    if isinstance(node, dict):
        for v in node.values():
            _strings(v, out)
    elif isinstance(node, list):
        for v in node:
            _strings(v, out)
    elif isinstance(node, str) and not node.startswith(("http", "/")):
        text = node.strip()
        if len(text) >= 20 or (len(text) >= 2 and _HANGUL.search(text)):
            out.append(_strip_html(text))


def from_next_data(page: str) -> str | None:
    match = _NEXT_RE.search(page)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    found: list[str] = []
    _strings(data.get("props", data), found)
    seen: set[str] = set()
    unique = [s for s in found if not (s in seen or seen.add(s))]
    return "\n".join(unique) or None


def extract(page: str) -> str:
    for strategy in (from_json_ld, from_next_data):
        if (text := strategy(page)) and text.strip():
            return text
    return trafilatura.extract(page, include_comments=False, include_tables=True) or ""


def judge(text: str, min_chars: int) -> str | None:
    """Failure reason for extracted text, or None when it is a usable posting."""
    lowered = text.lower()
    signals = sum(lowered.count(s) for s in LOGIN_SIGNALS)
    if signals and len(text) < max(min_chars * 2, 600):
        return "로그인 필요"
    if len(text.strip()) < min_chars:
        return "본문이 너무 짧음"
    return None


def decode(resp: httpx.Response) -> str:
    """Header charset, else ``<meta charset>``, else UTF-8, else CP949. Older Korean sites
    often send plain ``text/html`` with an EUC-KR body, which httpx would read as UTF-8."""
    if resp.charset_encoding:
        return resp.text
    body = resp.content
    meta = _META_CHARSET.search(body[:4096])
    for enc in ([meta.group(1).decode("ascii")] if meta else []) + ["utf-8", "cp949"]:
        try:
            return body.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return resp.text


def fetch(
    url: str, cfg: FetchConfig, client: httpx.Client, *, base_delay: float = 1.0
) -> FetchResult:
    @retryable(retry_on=(_Retry,), max_attempts=3, base_delay=base_delay, target="fetch:posting")
    def _get() -> httpx.Response:
        try:
            resp = client.get(
                url,
                headers={"User-Agent": cfg.user_agent, "Accept-Language": "ko,en;q=0.8"},
                timeout=cfg.timeout_s,
                follow_redirects=True,
            )
        except httpx.TransportError as exc:
            raise _Retry(f"network error: {type(exc).__name__}") from None
        if resp.status_code >= 500 or resp.status_code == 429:
            raise _Retry(f"HTTP {resp.status_code}")
        return resp

    try:
        resp = _get()
    except _Retry as exc:
        log.warning("fetch_failed", extra={"fields": {"error": str(exc)}})
        return FetchResult("failed", reason=str(exc))
    if not resp.is_success:
        return FetchResult("failed", reason=f"HTTP {resp.status_code}")
    text = extract(decode(resp))
    if reason := judge(text, cfg.min_chars):
        return FetchResult("failed", text=text, reason=reason)
    return FetchResult("ok", text=text)
