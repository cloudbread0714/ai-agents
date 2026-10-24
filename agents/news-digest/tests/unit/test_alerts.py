from datetime import UTC, datetime

from news_digest.alerts import build_alert_payload, build_warning_payload, run_url
from news_digest.models import RunResult, RunStatus, SourceResult

NOW = datetime(2026, 10, 25, 23, 3, tzinfo=UTC)
GH = {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "o/r", "GITHUB_RUN_ID": "42"}


def _result(**kw) -> RunResult:
    base = dict(
        run_at=NOW,
        status=RunStatus.COLLECT_FAILED,
        stage="collect",
        error="all 2 sources failed",
        candidate_count=0,
        source_results=[
            SourceResult(source="A", ok=False, error="HTTP 500"),
            SourceResult(source="B", ok=False, error="ConnectTimeout"),
        ],
    )
    base.update(kw)
    return RunResult(**base)


def _text(payload) -> str:
    parts = [payload["text"]]
    for block in payload["blocks"]:
        if "text" in block:
            parts.append(block["text"]["text"])
        for el in block.get("elements", []):
            parts.append(el["text"])
    return "\n".join(parts)


def test_alert_contains_status_stage_cause_time_and_sources():
    payload = build_alert_payload(_result(), tz="Asia/Seoul", env=GH)
    text = _text(payload)
    assert payload["text"] == "⚠️ news-digest COLLECT_FAILED"
    assert "*⚠️ news-digest: COLLECT_FAILED*" in text
    assert "단계: collect" in text
    assert "원인: all 2 sources failed" in text
    assert "실행: 2026-10-26 08:03 KST" in text
    assert "후보 0건" in text
    assert "실패 소스: A, B" in text
    assert "<https://github.com/o/r/actions/runs/42|GitHub Actions 실행 로그>" in text


def test_run_url_only_when_github_env_present():
    assert run_url({}) is None
    assert run_url(GH) == "https://github.com/o/r/actions/runs/42"
    payload = build_alert_payload(_result(), tz="Asia/Seoul", env={})
    assert "GitHub Actions" not in _text(payload)


def test_alert_masks_secrets_in_error():
    result = _result(
        status=RunStatus.SELECT_FAILED,
        stage="select",
        error="boom https://hooks.slack.com/services/T/B/XYZ sk-ant-abc123",
    )
    text = _text(build_alert_payload(result, tz="Asia/Seoul", env={}))
    assert "XYZ" not in text and "abc123" not in text


def test_unexpected_error_alert_has_title():
    result = _result(status=None, stage="unknown", error="RuntimeError: x")
    assert build_alert_payload(result, tz="Asia/Seoul", env={})["text"] == (
        "⚠️ news-digest UNEXPECTED_ERROR"
    )


def test_warning_payload_lists_each_warning():
    result = _result(
        status=RunStatus.POSTED,
        stage=None,
        error=None,
        candidate_count=12,
        warnings=["partial collect: A, B", "low relevance: 모든 후보의 관련도가 낮음"],
    )
    text = _text(build_warning_payload(result, tz="Asia/Seoul", env={}))
    assert "WARNING" in text
    assert "• partial collect: A, B" in text
    assert "• low relevance" in text
    assert "후보 12건" in text
