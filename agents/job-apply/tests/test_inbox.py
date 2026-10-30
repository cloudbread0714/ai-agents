import json

from ja_support.fake_slack import BOT, FakeSlack, install
from ja_support.meta import make_folder
from ja_support.samples import make_posting_html, posting_text

LINK = "https://jobs.example.com/p/{}"


def _png_bytes() -> bytes:
    import pymupdf

    return pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), False).tobytes("png")


_PNG = _png_bytes()


def _channel(httpx_mock):
    slack = install(httpx_mock, FakeSlack())
    slack.add(
        "1000.000001",
        f"이거 보자 <{LINK.format(1)}|공고1>",
        reactions={"white_check_mark": {"U0ME"}},
    )
    slack.add("1000.000002", f"<{LINK.format(2)}> 그리고 <{LINK.format(22)}|참고>")
    slack.add("1000.000003", posting_text())  # long text, no link
    slack.add("1000.000004", "점심 뭐 먹지")  # chat
    slack.add("1000.000005", f"<{LINK.format(5)}>")
    slack.add("1000.000006", "봇 공지", bot_id="B0", user=BOT)
    slack.add("1000.000007", "입장", subtype="channel_join")
    return slack


def _ok(httpx_mock, n):
    httpx_mock.add_response(url=LINK.format(n), text=make_posting_html("jsonld"))


def test_states_selection_and_cache(job, httpx_mock):
    slack = _channel(httpx_mock)
    _ok(httpx_mock, 2)
    code, res, _ = job("inbox", "--limit", "2")
    assert code == 0
    assert [i["id"] for i in res["items"]] == [
        "1000.000002",
        "1000.000003",
    ]  # oldest first, done skipped
    first, second = res["items"]
    assert (first["url"], first["fetch"], first["state"]) == (LINK.format(2), "ok", "new")
    assert (second["url"], second["fetch"]) == (None, "skipped")
    assert (
        res["excluded_non_posting"] == 1
        and res["awaiting_body"] == []
        and res["requested_now"] == []
    )
    cached = json.loads((job.root / ".job-state/inbox/1000.000002.json").read_text())
    assert cached["extra_urls"] == [LINK.format(22)] and cached["origin"] == "slack"
    assert (job.root.parents[1] / second["text_path"]).read_text().strip() == posting_text().strip()
    assert not slack.calls_of("reactions.add")


def test_duplicate_of_from_done_folders(job, httpx_mock):
    _channel(httpx_mock)
    _ok(httpx_mock, 2)
    make_folder(
        job.root / "applications",
        "2026-10-01_가상테크_백엔드",
        status="done",
        url_key=LINK.format(2),
    )
    _code, res, _ = job("inbox", "--limit", "1")
    assert (
        res["items"][0]["duplicate_of"]
        == "agents/job-apply/applications/2026-10-01_가상테크_백엔드"
    )


def test_fetch_failure_asks_for_body_and_keeps_going(job, httpx_mock):
    slack = _channel(httpx_mock)
    httpx_mock.add_response(url=LINK.format(2), status_code=403)
    _ok(httpx_mock, 5)
    _code, res, _ = job("inbox")
    assert [i["id"] for i in res["items"]] == ["1000.000003", "1000.000005"]
    assert res["requested_now"] == ["1000.000002"]
    assert slack.calls_of("reactions.add") == [
        {"channel": "C0JOB", "timestamp": "1000.000002", "name": "question"}
    ]
    [reply] = slack.calls_of("chat.postMessage")
    assert reply["thread_ts"] == "1000.000002" and "(사유: HTTP 403)" in reply["text"]


def test_image_body_is_kept_for_the_session(job, httpx_mock, monkeypatch):
    from job_apply import fetch as fetch_mod

    slack = _channel(httpx_mock)
    got = fetch_mod.FetchResult(
        "images", text="제목", reason="본문이 이미지로 게시됨", images=[_PNG]
    )
    monkeypatch.setattr(fetch_mod, "fetch", lambda *a, **k: got)
    _code, res, _ = job("inbox", "--limit", "1")
    [item] = res["items"]
    assert (item["id"], item["fetch"]) == ("1000.000002", "images")
    assert item["images"] == ["agents/job-apply/.job-state/inbox/1000.000002/01-1.png"]
    assert not slack.calls_of("reactions.add") and not slack.calls_of("chat.postMessage")


def test_limit_is_not_refilled_after_a_failure(job, httpx_mock):
    _channel(httpx_mock)
    httpx_mock.add_response(url=LINK.format(2), status_code=403)
    _code, res, _ = job("inbox", "--limit", "2")
    assert [i["id"] for i in res["items"]] == ["1000.000003"]  # FR-003: 5 is not pulled in


def test_awaiting_body_then_body_provided(job, httpx_mock):
    slack = _channel(httpx_mock)
    msg = slack.messages["1000.000002"]
    msg.reactions["question"] = {BOT}
    msg.replies.append({"ts": "1000.1", "text": "❓ 요청", "user": BOT, "bot_id": "B0"})
    _code, res, _ = job("inbox", "--limit", "1")
    assert res["awaiting_body"] == [{"id": "1000.000002", "url": LINK.format(2)}]
    assert [i["id"] for i in res["items"]] == ["1000.000003"]
    assert not slack.calls_of("reactions.add") and not slack.calls_of("chat.postMessage")

    msg.replies += [
        {"ts": "1000.2", "text": "공고 본문 1부", "user": "U0ME"},
        {"ts": "1000.3", "text": "공고 본문 2부", "user": "U0ME"},
        {"ts": "1000.4", "text": "봇 메모", "user": "U0X", "bot_id": "B9"},
    ]
    _code, res, _ = job("inbox", "--limit", "1")
    [item] = res["items"]
    assert (item["id"], item["state"], item["fetch"]) == ("1000.000002", "body_provided", "skipped")
    assert (
        job.root.parents[1] / item["text_path"]
    ).read_text().strip() == "공고 본문 1부\n\n공고 본문 2부"
    cached = json.loads((job.root / ".job-state/inbox/1000.000002.json").read_text())
    assert cached["url_key"] == LINK.format(2)  # dedup still by the original link


def test_needs_token_and_channel(job):
    job.environ = {}
    code, res, out = job("inbox")
    assert code == 5 and "SLACK_BOT_TOKEN" in out


def test_slack_escaped_ampersands_are_unescaped():
    from job_apply.inbox import unwrap

    text, urls = unwrap(
        "보자 &lt;신입&gt; <https://x.example/v?a=1&amp;b=2|공고> https://y.example/?c=3&amp;d=4"
    )
    assert urls == ["https://x.example/v?a=1&b=2", "https://y.example/?c=3&d=4"]
    assert text == "보자 <신입> https://x.example/v?a=1&b=2 https://y.example/?c=3&d=4"
