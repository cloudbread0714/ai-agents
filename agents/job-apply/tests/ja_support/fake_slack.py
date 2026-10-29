"""A stateful #job-apply for pytest-httpx: history, replies, reactions, posts and the
two-step file upload. Requests are recorded in order as (method, params)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import parse_qs

import httpx

BOT = "U0BOT"
ME = "U0ME"


@dataclass
class Msg:
    ts: str
    text: str
    user: str = ME
    bot_id: str | None = None
    subtype: str | None = None
    reactions: dict[str, set[str]] = field(default_factory=dict)
    replies: list[dict] = field(default_factory=list)


class FakeSlack:
    def __init__(self) -> None:
        self.messages: dict[str, Msg] = {}
        self.calls: list[tuple[str, dict]] = []
        self.fail: dict[str, int] = {}  # method → remaining 5xx responses
        self.uploads: dict[str, bytes] = {}
        self._n = 0

    def add(self, ts: str, text: str, **kw) -> Msg:
        self.messages[ts] = Msg(ts, text, **kw)
        return self.messages[ts]

    def calls_of(self, method: str) -> list[dict]:
        return [p for m, p in self.calls if m == method]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://files.slack.com/"):
            self.calls.append(("upload", {"url": url}))
            self.uploads[url] = request.read()
            return self._maybe_fail("upload") or httpx.Response(200, text="OK")
        method = request.url.path.rsplit("/", 1)[-1]
        if request.method == "GET":
            params = dict(request.url.params)
        elif request.headers.get("content-type", "").startswith("application/json"):
            params = json.loads(request.read())
        else:
            params = {k: v[0] for k, v in parse_qs(request.read().decode()).items()}
        self.calls.append((method, params))
        if failed := self._maybe_fail(method):
            return failed
        return httpx.Response(200, json=getattr(self, "_" + method.replace(".", "_"))(params))

    def _maybe_fail(self, method):
        if self.fail.get(method, 0) > 0:
            self.fail[method] -= 1
            return httpx.Response(503)
        return None

    def _auth_test(self, p):
        return {"ok": True, "user_id": BOT}

    def _conversations_history(self, p):
        msgs = sorted(self.messages.values(), key=lambda m: -float(m.ts))
        out = []
        for m in msgs:
            item = {"ts": m.ts, "text": m.text, "user": m.user}
            if m.bot_id:
                item["bot_id"] = m.bot_id
            if m.subtype:
                item["subtype"] = m.subtype
            if m.reactions:
                item["reactions"] = [
                    {"name": n, "users": sorted(u), "count": len(u)} for n, u in m.reactions.items()
                ]
            out.append(item)
        return {
            "ok": True,
            "messages": out[: int(p.get("limit", 200))],
            "response_metadata": {"next_cursor": ""},
        }

    def _conversations_replies(self, p):
        m = self.messages[p["ts"]]
        return {"ok": True, "messages": [{"ts": m.ts, "text": m.text, "user": m.user}, *m.replies]}

    def _reactions_add(self, p):
        users = self.messages[p["timestamp"]].reactions.setdefault(p["name"], set())
        if BOT in users:
            return {"ok": False, "error": "already_reacted"}
        users.add(BOT)
        return {"ok": True}

    def _chat_postMessage(self, p):
        self._n += 1
        ts = f"{p.get('thread_ts', '9')}.{self._n:03d}"
        if p.get("thread_ts"):
            self.messages[p["thread_ts"]].replies.append(
                {"ts": ts, "text": p["text"], "user": BOT, "bot_id": "B0"}
            )
        return {"ok": True, "channel": p["channel"], "ts": ts}

    def _files_getUploadURLExternal(self, p):
        self._n += 1
        return {
            "ok": True,
            "upload_url": f"https://files.slack.com/up/{self._n}",
            "file_id": f"F{self._n}",
        }

    def _files_completeUploadExternal(self, p):
        return {"ok": True, "files": json.loads(p["files"])}


def install(httpx_mock, slack: FakeSlack) -> FakeSlack:
    import re

    httpx_mock.add_callback(
        slack, url=re.compile(r"https://(slack\.com/api|files\.slack\.com)/.*"), is_reusable=True
    )
    return slack
