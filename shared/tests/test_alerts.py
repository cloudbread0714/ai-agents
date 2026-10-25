from shared.alerts import alert_payload, run_url, warning_payload

GH = {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "o/r", "GITHUB_RUN_ID": "7"}


def _text(payload) -> str:
    parts = [payload["text"]]
    for block in payload["blocks"]:
        if "text" in block:
            parts.append(block["text"]["text"])
        parts += [el["text"] for el in block.get("elements", [])]
    return "\n".join(parts)


def test_run_url_needs_all_github_vars():
    assert run_url({}) is None
    assert run_url({"GITHUB_RUN_ID": "7"}) is None
    assert run_url(GH) == "https://github.com/o/r/actions/runs/7"


def test_alert_payload_shape():
    payload = alert_payload(
        "lab", "POST_FAILED", stage="post", cause="HTTP 500", context_parts=["실행: now"], env=GH
    )
    text = _text(payload)
    assert payload["text"] == "⚠️ lab POST_FAILED"
    assert "*⚠️ lab: POST_FAILED*\n단계: post\n원인: HTTP 500" in text
    assert "실행: now · <https://github.com/o/r/actions/runs/7|GitHub Actions 실행 로그>" in text


def test_alert_defaults_unknown_and_omits_link_outside_actions():
    text = _text(alert_payload("lab", "X", stage=None, cause=None, context_parts=[], env={}))
    assert "단계: unknown" in text and "원인: unknown" in text
    assert "GitHub Actions" not in text


def test_secrets_masked_and_mrkdwn_escaped_everywhere():
    secret = "https://hooks.slack.com/services/T/B/XYZ"
    payload = alert_payload(
        "lab",
        "X",
        stage="a<b",
        cause=f"boom {secret} sk-ant-abc",
        context_parts=[f"<{secret}>"],
        env={},
    )
    text = _text(payload)
    assert "XYZ" not in text and "sk-ant-abc" not in text
    assert "a&lt;b" in text
    assert "&lt;https://hooks.slack.com/services/***" in text  # masking runs to the next space


def test_warning_payload_lists_each_warning():
    payload = warning_payload("lab", ["one", "t<wo"], context_parts=["c"], env={})
    text = _text(payload)
    assert payload["text"] == "⚠️ lab WARNING"
    assert "*⚠️ lab: WARNING* (게시는 완료됨)\n• one\n• t&lt;wo" in text
