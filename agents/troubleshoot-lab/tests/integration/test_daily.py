"""Plan-based posting through the CLI with Slack mocked (contracts/cli.md 게시 명령)."""

import io
import json
import logging
from datetime import UTC, datetime

import pytest

from tl_support import LAB_HOOK, TEST_HOOK, write_scenario

MONDAY = datetime(2026, 10, 25, 23, 40, tzinfo=UTC)  # Monday 10/26 08:40 KST
SATURDAY_UTC_SUNDAY_KST = datetime(2026, 10, 31, 23, 40, tzinfo=UTC)  # Sunday 11/01 08:40 KST
ENV = {"SLACK_WEBHOOK_LAB_URL": LAB_HOOK, "SLACK_WEBHOOK_URL_TEST": TEST_HOOK}


def daily(lab_root, *args, env=ENV, now=MONDAY):
    from troubleshoot_lab.cli import main

    out = io.StringIO()
    code = main(["daily", *args], lab_root=lab_root, environ=env, now=now, out=out, base_delay=0)
    return code, json.loads(out.getvalue().strip().splitlines()[-1]), out.getvalue()


def posted(lab_root):
    path = lab_root / "data" / "posted.json"
    return json.loads(path.read_text()) if path.exists() else {"daily": [], "weekly": []}


def bodies(httpx_mock, url):
    return [json.loads(r.content) for r in httpx_mock.get_requests(url=url)]


def test_first_post_is_day_one_and_recorded(lab_root, httpx_mock):
    httpx_mock.add_response(url=LAB_HOOK, text="ok", is_reusable=True)
    code, summary, _ = daily(lab_root, "--target", "lab")
    assert code == 0 and summary["status"] == "POSTED"
    assert summary["daily"] | {} == {
        "status": "POSTED",
        "kind": "day",
        "day": 1,
        "main_id": "c-one",
        "second_id": None,
        "backlog": [],
        "error": None,
    }
    assert bodies(httpx_mock, LAB_HOOK)[0]["text"] == "📚 1일 차 · 1주 차: 주제 1"
    record = posted(lab_root)["daily"][0]
    assert (record["date_kst"], record["kind"], record["day"], record["main_kind"]) == (
        "2026-10-26",
        "day",
        1,
        "mission",
    )


def test_next_day_follows_the_plan(lab_root, httpx_mock):
    httpx_mock.add_response(url=LAB_HOOK, text="ok", is_reusable=True)
    daily(lab_root, "--target", "lab")
    _, summary, _ = daily(lab_root, "--target", "lab", now=MONDAY.replace(day=26))
    assert (summary["daily"]["day"], summary["daily"]["main_id"]) == (2, "d-easy")


def test_second_run_same_day_is_already_posted(lab_root, httpx_mock):
    httpx_mock.add_response(url=LAB_HOOK, text="ok", is_reusable=True)
    daily(lab_root, "--target", "lab")
    code, summary, _ = daily(lab_root, "--target", "lab")
    assert code == 0 and summary["status"] == "ALREADY_POSTED"
    assert len(httpx_mock.get_requests()) == 1


def test_test_target_prefixes_and_never_records(lab_root, httpx_mock):
    httpx_mock.add_response(url=TEST_HOOK, text="ok", is_reusable=True)
    daily(lab_root, "--target", "test")
    assert bodies(httpx_mock, TEST_HOOK)[0]["text"].startswith("[TEST] ")
    assert posted(lab_root)["daily"] == []


def test_post_failure_alerts_test_channel(lab_root, httpx_mock):
    httpx_mock.add_response(url=LAB_HOOK, status_code=404, text="no_service", is_reusable=True)
    httpx_mock.add_response(url=TEST_HOOK, text="ok", is_reusable=True)
    code, summary, _ = daily(lab_root, "--target", "lab")
    assert code == 1 and summary["status"] == "POST_FAILED"
    assert bodies(httpx_mock, TEST_HOOK)[0]["text"] == "⚠️ troubleshoot-lab POST_FAILED"
    assert posted(lab_root)["daily"] == []


def test_invalid_scenario_warns_but_still_posts(lab_root, httpx_mock):
    write_scenario(lab_root, {"id": "broken", "title": "t"}, field_dir="linux", scripts=False)
    httpx_mock.add_response(url=TEST_HOOK, text="ok", is_reusable=True)
    httpx_mock.add_response(url=LAB_HOOK, text="ok", is_reusable=True)
    code, summary, _ = daily(lab_root, "--target", "lab")
    assert code == 0 and any("broken" in w for w in summary["warnings"])
    assert bodies(httpx_mock, TEST_HOOK)[0]["text"] == "⚠️ troubleshoot-lab WARNING"


def test_invalid_plan_fails_with_alert(lab_root, httpx_mock):
    (lab_root / "curriculum" / "plan.yaml").write_text("days: []\n")
    httpx_mock.add_response(url=TEST_HOOK, text="ok", is_reusable=True)
    code, summary, _ = daily(lab_root, "--target", "lab")
    assert code == 1 and summary["status"] == "NO_SCENARIO"
    texts = [b["text"] for b in bodies(httpx_mock, TEST_HOOK)]
    assert "⚠️ troubleshoot-lab WARNING" in texts and "⚠️ troubleshoot-lab NO_SCENARIO" in texts


@pytest.mark.parametrize(
    "args,env",
    [
        (["--target", "lab"], {"SLACK_WEBHOOK_URL_TEST": TEST_HOOK}),
        (["--target", "test"], {}),
        (["--target", "lab", "--force"], ENV),
        (["--target", "lab", "--today", "2026-11-01"], ENV),
    ],
)
def test_usage_errors_exit_2(lab_root, args, env, capsys):
    from troubleshoot_lab.cli import main

    assert main(["daily", *args], lab_root=lab_root, environ=env, out=io.StringIO()) == 2
    assert "hooks.slack.com" not in capsys.readouterr().err


def test_dry_run_prints_and_sends_nothing(lab_root, httpx_mock):
    code, summary, output = daily(lab_root, "--dry-run", "--force", env={})
    assert code == 0 and "개념 미션" in output
    assert httpx_mock.get_requests() == []


def test_webhook_urls_never_logged(lab_root, httpx_mock, caplog):
    httpx_mock.add_response(url=LAB_HOOK, text="ok", is_reusable=True)
    with caplog.at_level(logging.DEBUG):
        daily(lab_root, "--target", "lab")
    assert "LABLABLAB" not in caplog.text and "TESTTESTTEST" not in caplog.text


def test_sunday_kst_posts_daily_then_weekly(lab_root, httpx_mock):
    httpx_mock.add_response(url=LAB_HOOK, text="ok", is_reusable=True)
    code, summary, _ = daily(lab_root, "--target", "lab", now=SATURDAY_UTC_SUNDAY_KST)
    assert code == 0 and summary["weekly"]["status"] == "POSTED"
    sent = bodies(httpx_mock, LAB_HOOK)
    assert sent[0]["text"].startswith("📚") and sent[1]["text"].startswith("📊")
    record = posted(lab_root)
    assert record["daily"][0]["date_kst"] == "2026-11-01"
    assert record["weekly"][0]["week_start_kst"] == "2026-10-26"


def test_post_modes_and_weekly_dedup(lab_root, httpx_mock):
    httpx_mock.add_response(url=TEST_HOOK, text="ok", is_reusable=True)
    _, summary, _ = daily(lab_root, "--target", "test")
    assert summary["weekly"] is None
    _, summary, _ = daily(lab_root, "--target", "test", "--post", "weekly")
    assert summary["daily"] is None and summary["weekly"]["status"] == "POSTED"
    httpx_mock.add_response(url=LAB_HOOK, text="ok", is_reusable=True)
    daily(lab_root, "--target", "lab", "--post", "weekly", now=MONDAY)
    _, summary, _ = daily(lab_root, "--target", "lab", now=SATURDAY_UTC_SUNDAY_KST)
    assert (
        summary["daily"]["status"] == "POSTED" and summary["weekly"]["status"] == "ALREADY_POSTED"
    )
