"""US3 + US4: /job-run's deterministic steps against a fake #job-apply."""

import json

from ja_support import session
from ja_support.fake_slack import FakeSlack, install
from ja_support.samples import make_posting_html, posting_text

LINK = "https://jobs.example.com/p/{}"


def _channel(httpx_mock):
    slack = install(httpx_mock, FakeSlack())
    slack.add("1000.000001", f"<{LINK.format(1)}>", reactions={"white_check_mark": {"U0ME"}})
    slack.add("1000.000002", f"<{LINK.format(2)}> <{LINK.format(22)}>")
    slack.add("1000.000003", posting_text())
    slack.add("1000.000004", f"<{LINK.format(4)}>")
    slack.add("1000.000005", "잡담")
    httpx_mock.add_response(url=LINK.format(2), text=make_posting_html("jsonld"), is_optional=True)
    return slack


def _process(job, item_id, company, role):
    code, res, out = job("init", item_id, "--company", company, "--role", role)
    assert code == 0, out
    folder = job.root.parents[1] / res["folder"]
    session.write(folder)
    assert job("apply", str(folder))[0] == 0
    return folder


def test_two_oldest_processed_and_marked(job, httpx_mock):
    slack = _channel(httpx_mock)
    code, res, _ = job("inbox", "--limit", "2")
    assert [i["id"] for i in res["items"]] == ["1000.000002", "1000.000003"]
    for item_id, company in (("1000.000002", "가상테크"), ("1000.000003", "샘플랩스")):
        folder = _process(job, item_id, company, "백엔드 개발자")
        code, done, out = job("complete", str(folder))
        assert code == 0, out
        assert done["status"] == "done" and done["reply_ts"]
        meta = json.loads((folder / "meta.json").read_text())["slack"]
        assert meta == {"reply_ts": done["reply_ts"], "files_uploaded": True, "reacted": True}

    order = [m for m, _ in slack.calls if m not in ("conversations.history", "auth.test")]
    assert (
        order
        == [
            "chat.postMessage",
            "files.getUploadURLExternal",
            "upload",
            "files.getUploadURLExternal",
            "upload",
            "files.completeUploadExternal",
            "reactions.add",
        ]
        * 2
    )
    first_reply = slack.calls_of("chat.postMessage")[0]
    assert (
        first_reply["thread_ts"] == "1000.000002"
        and f"처리하지 않은 링크: {LINK.format(22)}" in first_reply["text"]
    )
    complete = slack.calls_of("files.completeUploadExternal")[0]
    assert [f["title"] for f in json.loads(complete["files"])] == [
        "가상테크_백엔드-개발자_resume.pdf",
        "가상테크_백엔드-개발자_portfolio.pdf",
    ]
    assert complete["thread_ts"] == "1000.000002"

    httpx_mock.add_response(url=LINK.format(4), text=make_posting_html("jsonld"))
    code, res, _ = job("inbox", "--limit", "2")
    assert [i["id"] for i in res["items"]] == ["1000.000004"]  # SC-005: the two are done now


def test_upload_failure_then_resume_without_second_reply(job, httpx_mock):
    slack = _channel(httpx_mock)
    job("inbox", "--limit", "1")
    folder = _process(job, "1000.000002", "가상테크", "백엔드 개발자")
    slack.fail["upload"] = 3
    code, res, out = job("complete", str(folder))
    assert code == 7 and "다시 실행하면 이어서" in out
    meta = json.loads((folder / "meta.json").read_text())
    assert (
        meta["status"] == "in_progress"
        and meta["slack"]["reply_ts"]
        and not meta["slack"]["reacted"]
    )
    assert not slack.calls_of("reactions.add")
    code, _res, _ = job("complete", str(folder))
    assert code == 0
    assert (
        len(slack.calls_of("chat.postMessage")) == 1 and len(slack.calls_of("reactions.add")) == 1
    )


def test_skip_duplicate_and_expired(job, httpx_mock):
    slack = _channel(httpx_mock)
    job("inbox", "--limit", "1")
    first = _process(job, "1000.000002", "가상테크", "백엔드 개발자")
    assert job("complete", str(first))[0] == 0

    slack.add("1000.000009", f"<{LINK.format(2)}?utm_source=slack>")
    httpx_mock.add_response(
        url=LINK.format(2) + "?utm_source=slack", text=make_posting_html("jsonld")
    )
    httpx_mock.add_response(url=LINK.format(4), text=make_posting_html("jsonld"))
    _code, res, _ = job("inbox")
    item = next(i for i in res["items"] if i["id"] == "1000.000009")
    assert item["duplicate_of"].endswith("2026-10-27_가상테크_백엔드-개발자")
    assert job("skip", "1000.000009", "--reason", "duplicate")[0] == 0
    reply = slack.calls_of("chat.postMessage")[-1]
    assert reply["thread_ts"] == "1000.000009" and reply["text"].startswith(
        "🔁 이미 처리한 공고예요 →"
    )
    assert "1000.000009" in [c["timestamp"] for c in slack.calls_of("reactions.add")]

    before = len(slack.calls)
    assert job("skip", "1000.000003", "--reason", "expired")[0] == 0
    assert len(slack.calls) == before
    assert job("skip", "1000.000003", "--reason", "expired", "--mark-done")[0] == 2
    assert (
        job(
            "skip", "1000.000003", "--reason", "expired", "--mark-done", "--deadline", "2026-10-20"
        )[0]
        == 0
    )
    assert (
        slack.calls_of("chat.postMessage")[-1]["text"]
        == "⏰ 마감(2026-10-20)이 지나 처리하지 않았어요."
    )
    assert slack.messages["1000.000003"].reactions["white_check_mark"]


def test_body_provided_posting_end_to_end(job, httpx_mock):
    slack = _channel(httpx_mock)
    msg = slack.messages["1000.000004"]
    msg.reactions["question"] = {"U0BOT"}
    msg.replies.append({"ts": "1000.5", "text": posting_text(), "user": "U0ME"})
    _code, res, _ = job("inbox")
    item = next(i for i in res["items"] if i["id"] == "1000.000004")
    assert (item["state"], item["fetch"]) == ("body_provided", "skipped")
    folder = _process(job, "1000.000004", "가상테크", "데이터 엔지니어")
    assert json.loads((folder / "meta.json").read_text())["posting"]["url_key"] == LINK.format(4)
    assert job("complete", str(folder))[0] == 0
    assert msg.reactions["white_check_mark"]
