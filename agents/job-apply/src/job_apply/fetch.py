"""Fetching a posting page and deciding "could not fetch" (research R8, FR-017).

JSON-LD ``JobPosting`` and ``__NEXT_DATA__`` are tried before trafilatura. A failure is
not an exception: it comes back as ``FetchResult(status="failed", reason=...)`` so the
caller can ask the user for the body.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

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
_OG_RE = re.compile(
    r"<meta[^>]+property=[\"']og:(title|description)[\"'][^>]+content=\"([^\"]*)\"", re.I
)
_IMG_SRC = re.compile(r"<img\b[^>]*?\bsrc=[\"']([^\"']+)[\"']", re.I)
MAX_IMAGES = 12
MAX_IMAGE_BYTES = 15 * 1024 * 1024
_JOBKOREA_GI = re.compile(r"/Recruit/GI_Read/(\d+)")


@dataclass
class FetchResult:
    status: str  # ok | images | failed
    text: str = ""
    reason: str | None = None
    # status "images": the posting body is pictures; the session reads them (research R8).
    images: list[bytes] = field(default_factory=list)


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


def detail_url(url: str) -> str | None:
    """Where a job board loads the posting body from, when the page itself is a shell.

    Saramin fetches it by script and JobKorea puts it in an iframe, so the page at
    ``url`` holds only site chrome.
    """
    parts = urlsplit(url)
    host = parts.hostname or ""
    if host.endswith("saramin.co.kr"):
        rec = parse_qs(parts.query).get("rec_idx")
        if rec and rec[0].isdigit():
            return f"https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx={rec[0]}"
    elif host.endswith("jobkorea.co.kr"):
        if match := _JOBKOREA_GI.search(parts.path):
            return f"https://www.jobkorea.co.kr/Recruit/GI_Read_Comt_Ifrm?Gno={match.group(1)}"
    return None


def og_summary(page: str) -> str:
    """og:title and og:description (company, role, deadline on most boards)."""
    found = dict((k.lower(), html_lib.unescape(v).strip()) for k, v in _OG_RE.findall(page))
    return "\n".join(found[k] for k in ("title", "description") if found.get(k))


def image_urls(page: str, base: str) -> list[str]:
    urls: list[str] = []
    for src in _IMG_SRC.findall(page):
        src = html_lib.unescape(src.strip())
        if src.startswith("data:"):
            continue
        full = urljoin(base, src)
        if full not in urls:
            urls.append(full)
    return urls


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
    def _get(target: str) -> httpx.Response:
        try:
            resp = client.get(
                target,
                headers={"User-Agent": cfg.user_agent, "Accept-Language": "ko,en;q=0.8"},
                timeout=cfg.timeout_s,
                follow_redirects=True,
            )
        except httpx.TransportError as exc:
            raise _Retry(f"network error: {type(exc).__name__}") from None
        if resp.status_code >= 500 or resp.status_code == 429:
            raise _Retry(f"HTTP {resp.status_code}")
        return resp

    def _page(target: str) -> tuple[str | None, str | None]:
        try:
            resp = _get(target)
        except _Retry as exc:
            log.warning("fetch_failed", extra={"fields": {"error": str(exc)}})
            return None, str(exc)
        if not resp.is_success:
            return None, f"HTTP {resp.status_code}"
        return decode(resp), None

    page, error = _page(url)
    if page is None:
        return FetchResult("failed", reason=error)
    detail = detail_url(url)
    if detail is None:
        text = extract(page)
    else:
        body, error = _page(detail)
        if body is None:
            return FetchResult("failed", reason=f"본문 페이지 {error}")
        text = "\n\n".join(p for p in (og_summary(page), extract(body)) if p)
    reason = judge(text, cfg.min_chars)
    if reason is None:
        return FetchResult("ok", text=text)
    if detail and reason == "본문이 너무 짧음" and (urls := image_urls(body, detail)):
        images = []
        for src in urls[:MAX_IMAGES]:
            try:
                resp = _get(src)
            except _Retry:
                continue
            kind = resp.headers.get("content-type", "")
            if (
                resp.is_success
                and kind.startswith("image/")
                and len(resp.content) <= MAX_IMAGE_BYTES
            ):
                images.append(resp.content)
        if images:
            return FetchResult("images", text=text, reason="본문이 이미지로 게시됨", images=images)
        reason = f"본문 이미지를 받지 못함 (이미지 {len(urls)}개)"
    return FetchResult("failed", text=text, reason=reason)
