import json
import logging

import httpx
import pytest

from shared.slack import (
    SlackApiError,
    SlackMessageGone,
    SlackSendError,
    add_reaction,
    auth_test,
    get_reactions,
    mask_webhook,
    post_message,
    send_webhook,
)

URL = "https://hooks.slack.com/services/T000/B000/SECRETSECRET"


def test_success_on_ok_body(httpx_mock):
    httpx_mock.add_response(url=URL, method="POST", text="ok")
    send_webhook(URL, {"text": "hi"}, base_delay=0)
    request = httpx_mock.get_request()
    assert request.read() == b'{"text":"hi"}'


def test_retries_429_and_5xx_then_succeeds(httpx_mock):
    httpx_mock.add_response(url=URL, status_code=429, text="rate_limited")
    httpx_mock.add_response(url=URL, status_code=503, text="unavailable")
    httpx_mock.add_response(url=URL, text="ok")
    send_webhook(URL, {"text": "hi"}, base_delay=0)
    assert len(httpx_mock.get_requests()) == 3


def test_400_fails_without_retry(httpx_mock):
    httpx_mock.add_response(url=URL, status_code=400, text="invalid_payload")
    with pytest.raises(SlackSendError, match="HTTP 400"):
        send_webhook(URL, {"text": "hi"}, base_delay=0)
    assert len(httpx_mock.get_requests()) == 1


def test_non_ok_body_is_failure(httpx_mock):
    httpx_mock.add_response(url=URL, status_code=200, text="no_text")
    with pytest.raises(SlackSendError):
        send_webhook(URL, {"text": "hi"}, base_delay=0)


def test_network_error_retried_then_raises_without_url(httpx_mock):
    for _ in range(3):
        httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    with pytest.raises(SlackSendError) as excinfo:
        send_webhook(URL, {"text": "hi"}, base_delay=0)
    assert "SECRETSECRET" not in str(excinfo.value)
    assert len(httpx_mock.get_requests()) == 3


def test_logs_never_contain_webhook_secret(httpx_mock, caplog):
    httpx_mock.add_response(url=URL, status_code=500, text="err")
    httpx_mock.add_response(url=URL, text="ok")
    with caplog.at_level(logging.DEBUG):
        send_webhook(URL, {"text": "hi"}, base_delay=0)
    assert caplog.records
    for record in caplog.records:
        assert "SECRETSECRET" not in record.getMessage()
        assert "SECRETSECRET" not in str(getattr(record, "fields", ""))


def test_mask_webhook():
    assert mask_webhook(URL) == "https://hooks.slack.com/services/***"


def test_escape_mrkdwn_and_link():
    from shared.slack import escape_mrkdwn, slack_link

    assert escape_mrkdwn("a & <b>") == "a &amp; &lt;b&gt;"
    link = slack_link("https://x.dev/a|b<c>", "AWS <blog>")
    assert link == "<https://x.dev/a%7Cb%3Cc%3E|AWS &lt;blog&gt;>"


# --- Web API ---------------------------------------------------------------------------

TOKEN = "xoxb-test-secret"
API = "https://slack.com/api/"


def _assert_bearer(request):
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in str(request.url)
    assert TOKEN.encode() not in request.read()


def test_auth_test_returns_bot_user_id(httpx_mock):
    httpx_mock.add_response(url=API + "auth.test", json={"ok": True, "user_id": "U0BOT"})
    assert auth_test(TOKEN, base_delay=0) == "U0BOT"
    _assert_bearer(httpx_mock.get_request())


def test_post_message_returns_location_and_sends_thread_ts(httpx_mock):
    httpx_mock.add_response(
        url=API + "chat.postMessage", json={"ok": True, "channel": "C0LAB", "ts": "1.2"}
    )
    payload = {"text": "hi", "blocks": []}
    assert post_message(TOKEN, "C0LAB", payload, thread_ts="1.0", base_delay=0) == ("C0LAB", "1.2")
    request = httpx_mock.get_request()
    _assert_bearer(request)
    assert json.loads(request.read()) == {
        "channel": "C0LAB",
        "text": "hi",
        "blocks": [],
        "thread_ts": "1.0",
    }


def test_get_reactions_maps_names_to_users(httpx_mock):
    httpx_mock.add_response(
        url=f"{API}reactions.get?channel=C0LAB&timestamp=1.2&full=true",
        json={
            "ok": True,
            "message": {
                "reactions": [
                    {"name": "white_check_mark", "users": ["U0ME", "U0BOT"], "count": 2},
                    {"name": "eyes", "users": ["U0X"], "count": 1},
                ]
            },
        },
    )
    assert get_reactions(TOKEN, "C0LAB", "1.2", base_delay=0) == {
        "white_check_mark": {"U0ME", "U0BOT"},
        "eyes": {"U0X"},
    }
    _assert_bearer(httpx_mock.get_request())


def test_get_reactions_without_any_is_empty(httpx_mock):
    httpx_mock.add_response(json={"ok": True, "message": {"ts": "1.2"}})
    assert get_reactions(TOKEN, "C0LAB", "1.2", base_delay=0) == {}


def test_add_reaction_true_then_already_reacted_false(httpx_mock):
    httpx_mock.add_response(url=API + "reactions.add", json={"ok": True})
    httpx_mock.add_response(
        url=API + "reactions.add", json={"ok": False, "error": "already_reacted"}
    )
    assert add_reaction(TOKEN, "C0LAB", "1.2", "white_check_mark", base_delay=0) is True
    assert add_reaction(TOKEN, "C0LAB", "1.2", "white_check_mark", base_delay=0) is False


def test_permanent_error_code_fails_without_retry(httpx_mock):
    httpx_mock.add_response(json={"ok": False, "error": "not_in_channel"})
    with pytest.raises(SlackApiError) as excinfo:
        post_message(TOKEN, "C0LAB", {"text": "hi"}, base_delay=0)
    assert excinfo.value.code == "not_in_channel"
    assert str(excinfo.value) == "chat.postMessage: not_in_channel"
    assert len(httpx_mock.get_requests()) == 1


def test_message_not_found_is_its_own_error(httpx_mock):
    httpx_mock.add_response(json={"ok": False, "error": "message_not_found"})
    with pytest.raises(SlackMessageGone):
        get_reactions(TOKEN, "C0LAB", "1.2", base_delay=0)


def test_429_then_success_is_retried(httpx_mock):
    httpx_mock.add_response(status_code=429, headers={"Retry-After": "1"})
    httpx_mock.add_response(json={"ok": True, "user_id": "U0BOT"})
    assert auth_test(TOKEN, base_delay=0) == "U0BOT"
    assert len(httpx_mock.get_requests()) == 2


def test_5xx_exhausted_raises_api_error(httpx_mock):
    for _ in range(3):
        httpx_mock.add_response(status_code=503)
    with pytest.raises(SlackApiError) as excinfo:
        auth_test(TOKEN, base_delay=0)
    assert excinfo.value.code == "HTTP 503"
    assert len(httpx_mock.get_requests()) == 3


def test_api_errors_and_logs_never_contain_token(httpx_mock, caplog):
    httpx_mock.add_response(status_code=500)
    httpx_mock.add_response(json={"ok": False, "error": "invalid_auth"})
    with caplog.at_level(logging.DEBUG), pytest.raises(SlackApiError) as excinfo:
        auth_test(TOKEN, base_delay=0)
    assert TOKEN not in str(excinfo.value)
    assert caplog.records
    for record in caplog.records:
        assert TOKEN not in record.getMessage()
        assert TOKEN not in str(getattr(record, "fields", ""))


def test_conversations_history_follows_cursor(httpx_mock):
    httpx_mock.add_response(
        url=f"{API}conversations.history?channel=C0JOB&limit=200",
        json={
            "ok": True,
            "messages": [{"ts": "3"}, {"ts": "2"}],
            "response_metadata": {"next_cursor": "c1"},
        },
    )
    httpx_mock.add_response(
        url=f"{API}conversations.history?channel=C0JOB&limit=200&cursor=c1",
        json={"ok": True, "messages": [{"ts": "1"}], "response_metadata": {"next_cursor": ""}},
    )
    from shared.slack import conversations_history

    assert [m["ts"] for m in conversations_history(TOKEN, "C0JOB", base_delay=0)] == [
        "3",
        "2",
        "1",
    ]


def test_conversations_history_limit_stops_early(httpx_mock):
    httpx_mock.add_response(
        url=f"{API}conversations.history?channel=C0JOB&limit=1",
        json={"ok": True, "messages": [{"ts": "3"}], "response_metadata": {"next_cursor": "c"}},
    )
    from shared.slack import conversations_history

    assert len(conversations_history(TOKEN, "C0JOB", limit=1, base_delay=0)) == 1


def test_conversations_replies_drops_parent(httpx_mock):
    httpx_mock.add_response(
        url=f"{API}conversations.replies?channel=C0JOB&ts=1.0&limit=200",
        json={"ok": True, "messages": [{"ts": "1.0"}, {"ts": "1.1", "text": "body"}]},
    )
    from shared.slack import conversations_replies

    assert conversations_replies(TOKEN, "C0JOB", "1.0", base_delay=0) == [
        {"ts": "1.1", "text": "body"}
    ]


def test_upload_files_two_urls_then_one_complete(httpx_mock):
    from urllib.parse import parse_qs

    from shared.slack import upload_files

    for n in (1, 2):
        httpx_mock.add_response(
            url=API + "files.getUploadURLExternal",
            json={"ok": True, "upload_url": f"https://files.slack.com/up/{n}", "file_id": f"F{n}"},
        )
        httpx_mock.add_response(url=f"https://files.slack.com/up/{n}", text=f"OK - {n}")
    httpx_mock.add_response(url=API + "files.completeUploadExternal", json={"ok": True})
    ids = upload_files(
        TOKEN,
        "C0JOB",
        [("a_resume.pdf", b"%PDF-1"), ("a_portfolio.pdf", b"%PDF-22")],
        thread_ts="1.0",
        base_delay=0,
    )
    assert ids == ["F1", "F2"]
    first = parse_qs(
        httpx_mock.get_requests(url=API + "files.getUploadURLExternal")[0].read().decode()
    )
    assert first == {"filename": ["a_resume.pdf"], "length": ["6"]}
    upload = httpx_mock.get_request(url="https://files.slack.com/up/2")
    assert "Authorization" not in upload.headers and b"%PDF-22" in upload.read()
    done = parse_qs(
        httpx_mock.get_request(url=API + "files.completeUploadExternal").read().decode()
    )
    assert json.loads(done["files"][0]) == [
        {"id": "F1", "title": "a_resume.pdf"},
        {"id": "F2", "title": "a_portfolio.pdf"},
    ]
    assert done["channel_id"] == ["C0JOB"] and done["thread_ts"] == ["1.0"]


def test_upload_failure_raises_api_error(httpx_mock):
    from shared.slack import upload_files

    httpx_mock.add_response(
        url=API + "files.getUploadURLExternal",
        json={"ok": True, "upload_url": "https://files.slack.com/up/1", "file_id": "F1"},
    )
    for _ in range(3):
        httpx_mock.add_response(url="https://files.slack.com/up/1", status_code=502)
    with pytest.raises(SlackApiError) as excinfo:
        upload_files(TOKEN, "C0JOB", [("a.pdf", b"x")], base_delay=0)
    assert excinfo.value.code == "HTTP 502"


def test_internal_error_code_is_retried(httpx_mock):
    httpx_mock.add_response(json={"ok": False, "error": "internal_error"})
    httpx_mock.add_response(json={"ok": True, "user_id": "U0BOT"})
    assert auth_test(TOKEN, base_delay=0) == "U0BOT"
