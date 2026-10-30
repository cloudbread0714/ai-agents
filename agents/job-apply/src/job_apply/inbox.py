"""Reading #job-apply and picking the postings to process (data-model §2, FR-002–FR-003,
FR-017–FR-018).

Message state is recomputed from reactions and threads on every run; nothing is stored
except the per-posting cache under ``.job-state/inbox/``.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from job_apply import dedup, images, report
from job_apply.config import Paths
from job_apply.fetch import FetchResult
from job_apply.models import FetchInfo, Posting
from shared.slack import (
    add_reaction,
    auth_test,
    conversations_history,
    conversations_replies,
    post_message,
)

KST = ZoneInfo("Asia/Seoul")
DONE, QUESTION = "white_check_mark", "question"
POSTING_MIN_CHARS = 200
_LINK = re.compile(r"<(https?://[^>|\s]+)(?:\|[^>]*)?>")
_BARE = re.compile(r"(?<![<|])\bhttps?://[^\s>]+")


@dataclass
class Message:
    ts: str
    text: str
    urls: list[str]
    reactions: set[str]
    state: str = "new"
    thread_body: str | None = None

    @property
    def posted_at(self) -> datetime:
        return datetime.fromtimestamp(float(self.ts), KST)

    @property
    def is_posting(self) -> bool:
        return bool(self.urls) or len(self.text.strip()) >= POSTING_MIN_CHARS


@dataclass
class InboxResult:
    items: list[dict[str, Any]] = field(default_factory=list)
    awaiting_body: list[dict[str, Any]] = field(default_factory=list)
    requested_now: list[str] = field(default_factory=list)
    excluded_non_posting: int = 0


def unwrap(text: str) -> tuple[str, list[str]]:
    """Slack ``<url|label>`` → url; returns the plain text and every URL in order.

    Slack escapes ``&``, ``<`` and ``>`` in message text, URLs included, so both are
    unescaped; a URL left with ``&amp;`` loses its query parameters.
    """
    urls: list[str] = []

    def keep(match: re.Match) -> str:
        urls.append(html.unescape(match.group(1)))
        return match.group(1)

    plain = _LINK.sub(keep, text)
    for bare in _BARE.findall(text):
        bare = html.unescape(bare)
        if bare not in urls:
            urls.append(bare)
    return html.unescape(plain), urls


def _is_user_message(m: dict[str, Any]) -> bool:
    return not m.get("bot_id") and m.get("subtype") in (None, "file_share")


def save_posting(paths: Paths, posting: Posting, text: str) -> Path:
    paths.inbox.mkdir(parents=True, exist_ok=True)
    (paths.inbox / f"{posting.id}.json").write_text(
        posting.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    text_path = paths.inbox / f"{posting.id}.txt"
    text_path.write_text(text.strip() + "\n", encoding="utf-8")
    return text_path


def save_images(paths: Paths, posting_id: str, blobs: list[bytes]) -> list[str]:
    """Body images under ``.job-state/inbox/<id>/``; repo-relative paths, empty when none
    could be read."""
    return [paths.rel(p) for p in images.save(blobs, paths.inbox / posting_id)]


def load_posting(paths: Paths, posting_id: str) -> tuple[Posting, str]:
    path = paths.inbox / f"{posting_id}.json"
    posting = Posting.model_validate_json(path.read_text(encoding="utf-8"))
    text = (paths.inbox / f"{posting_id}.txt").read_text(encoding="utf-8")
    return posting, text


def collect(
    paths: Paths,
    token: str,
    channel: str,
    limit: int | None,
    fetcher: Callable[[str], FetchResult],
    slack_kw: dict[str, Any],
) -> InboxResult:
    result = InboxResult()
    bot_id: str | None = None
    messages: list[Message] = []
    for raw in conversations_history(token, channel, **slack_kw):
        if not _is_user_message(raw):
            continue
        text, urls = unwrap(raw.get("text", ""))
        reactions = {r["name"] for r in raw.get("reactions", [])}
        msg = Message(ts=raw["ts"], text=text, urls=urls, reactions=reactions)
        if DONE in reactions:
            msg.state = "done"
        elif QUESTION in reactions:
            if bot_id is None:
                bot_id = auth_test(token, **slack_kw)
            replies = conversations_replies(token, channel, msg.ts, **slack_kw)
            bodies = [
                unwrap(r.get("text", ""))[0]
                for r in replies
                if not r.get("bot_id") and r.get("user") != bot_id and r.get("text", "").strip()
            ]
            msg.state, msg.thread_body = (
                ("body_provided", "\n\n".join(bodies)) if bodies else ("awaiting_body", None)
            )
        if not msg.is_posting:
            if msg.state != "done":
                result.excluded_non_posting += 1
            continue
        messages.append(msg)

    messages.sort(key=lambda m: float(m.ts))
    result.awaiting_body = [
        {"id": m.ts, "url": m.urls[0] if m.urls else None}
        for m in messages
        if m.state == "awaiting_body"
    ]
    targets = [m for m in messages if m.state in ("new", "body_provided")]
    if limit is not None:
        targets = targets[:limit]  # FR-003: no replacement for postings that fail below

    for m in targets:
        url = m.urls[0] if m.urls else None
        image_paths: list[str] = []
        if m.state == "body_provided":
            body, fetch = m.thread_body or "", FetchInfo(status="skipped")
        elif url:
            got = fetcher(url)
            if got.status == "images":
                image_paths = save_images(paths, m.ts, got.images)
                if not image_paths:
                    got.status, got.reason = "failed", "본문 이미지를 열지 못함"
            if got.status == "failed":
                add_reaction(token, channel, m.ts, QUESTION, **slack_kw)
                post_message(
                    token,
                    channel,
                    {"text": report.body_request(got.reason or "알 수 없음")},
                    thread_ts=m.ts,
                    **slack_kw,
                )
                result.requested_now.append(m.ts)
                continue
            body, fetch = got.text, FetchInfo(status=got.status, reason=got.reason)
        else:
            body, fetch = m.text, FetchInfo(status="skipped")
        key = dedup.key_for(url, body)
        done = dedup.find_done(paths.applications, key)
        posting = Posting(
            id=m.ts,
            origin="slack",
            message_ts=m.ts,
            posted_at=m.posted_at,
            url=url,
            extra_urls=m.urls[1:],
            url_key=key,
            fetch=fetch,
            duplicate_of=paths.rel(done) if done else None,
        )
        text_path = save_posting(paths, posting, body)
        result.items.append(
            {
                "id": m.ts,
                "posted_at": m.posted_at.isoformat(timespec="seconds"),
                "url": url,
                "state": m.state,
                "fetch": fetch.status,
                "duplicate_of": posting.duplicate_of,
                "text_path": paths.rel(text_path),
                "images": image_paths,
            }
        )
    return result


def to_json(result: InboxResult) -> dict[str, Any]:
    return json.loads(json.dumps(result.__dict__, ensure_ascii=False))
