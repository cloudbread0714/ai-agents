import logging

import httpx
import pytest

from shared.slack import SlackSendError, mask_webhook, send_webhook

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
