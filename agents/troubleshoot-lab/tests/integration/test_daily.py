"""Solve-gated posting through the CLI with Slack mocked (004 contracts/cli.md lab daily)."""

import io
import json
import logging
from datetime import UTC, datetime, timedelta

import pytest

from tl_support import TEST_HOOK, ev, hint_sentinel, progress_of, write_scenario
from troubleshoot_lab.progress import ProgressStore

MONDAY = datetime(2026, 10, 25, 23, 40, tzinfo=UTC)  # Monday 10/26 08:40 KST
SATURDAY_UTC_SUNDAY_KST = datetime(2026, 10, 31, 23, 40, tzinfo=UTC)  # Sunday 11/01 08:40 KST
TOKEN = "xoxb-test-secret"
ENV = {
    "SLACK_BOT_TOKEN": TOKEN,
    "SLACK_LAB_CHANNEL_ID": "C0LAB",
    "SLACK_USER_ID": "U0ME",
    "SLACK_WEBHOOK_URL_TEST": TEST_HOOK,
}
API = "https://slack.com/api/"
POST = API + "chat.postMessage"
REACTIONS = f"{API}reactions.get?channel=C0LAB&timestamp=100.1&full=true"
LEGACY_FIELDS = ("date_kst", "kind", "day", "main_kind", "main_id", "second_id", "posted_at")


def daily(lab_root, *args, env=ENV, now=MONDAY):
    from troubleshoot_lab.cli import main

    out = io.StringIO()
    code = main(["daily", *args], lab_root=lab_root, environ=env, now=now, out=out, base_delay=0)
    return code, json.loads(out.getvalue().strip().splitlines()[-1]), out.getvalue()


def posted(lab_root):
    path = lab_root / "data" / "posted.json"
    return json.loads(path.read_text()) if path.exists() else {"daily": [], "weekly": []}


def seed(lab_root, *records):
    path = lab_root / "data" / "posted.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 2, "daily": list(records), "weekly": []}))
    return path.read_bytes()


def open_record(date_kst="2026-10-26", main="d-easy", day=2, main_kind="scenario", **kw):
    return {
        "date_kst": date_kst,
        "kind": "day",
        "day": day,
        "main_kind": main_kind,
        "main_id": main,
        "second_id": None,
        "posted_at": "2026-10-25T23:40:00Z",
        "channel": "C0LAB",
        "ts": "100.1",
        "outcome": "open",
        **kw,
    }


def bodies(httpx_mock, url):
    return [json.loads(r.content) for r in httpx_mock.get_requests(url=url)]


def mock_post(httpx_mock, ts="200.1"):
    httpx_mock.add_response(url=POST, json={"ok": True, "channel": "C0LAB", "ts": ts})


def mock_gate(httpx_mock, reactions):
    httpx_mock.add_response(url=API + "auth.test", json={"ok": True, "user_id": "U0BOT"})
    httpx_mock.add_response(
        url=REACTIONS,
        json={
            "ok": True,
            "message": {"reactions": [{"name": n, "users": u} for n, u in reactions.items()]},
        },
    )


def on(day):
    return MONDAY + timedelta(days=day)


# --- US1: post, judge, remind ---------------------------------------------------------


def test_first_post_records_message_location(lab_root, httpx_mock):
    mock_post(httpx_mock, ts="100.1")
    code, summary, _ = daily(lab_root, "--target", "lab")
    assert code == 0 and summary["status"] == "POSTED"
    assert summary["daily"] == {
        "status": "POSTED",
        "kind": "day",
        "day": 1,
        "main_id": "c-one",
        "second_id": None,
        "resolved_id": None,
        "hint_included": None,
        "error": None,
    }
    sent = httpx_mock.get_request(url=POST)
    assert sent.headers["Authorization"] == f"Bearer {TOKEN}"
    body = json.loads(sent.content)
    assert body["channel"] == "C0LAB" and body["text"] == "📚 1일 차 · 1주 차: 주제 1"
    record = posted(lab_root)["daily"][0]
    assert (record["date_kst"], record["main_id"], record["channel"], record["ts"]) == (
        "2026-10-26",
        "c-one",
        "C0LAB",
        "100.1",
    )
    assert record["outcome"] == "open" and record["reminders"] == []


@pytest.mark.parametrize("by", ["U0ME", "U0BOT"])
def test_check_mark_by_learner_or_bot_solves_and_posts_next(lab_root, httpx_mock, by):
    seed(lab_root, open_record())
    mock_gate(httpx_mock, {"white_check_mark": [by]})
    mock_post(httpx_mock)
    code, summary, _ = daily(lab_root, "--target", "lab", now=on(1))
    assert code == 0 and summary["status"] == "POSTED"
    assert summary["daily"]["resolved_id"] == "d-easy" and summary["daily"]["day"] == 3
    first, second = posted(lab_root)["daily"]
    assert first["outcome"] == "solved" and first["resolved_at"] is not None
    assert second["outcome"] == "open" and second["ts"] == "200.1"
    assert "thread_ts" not in bodies(httpx_mock, POST)[0]


@pytest.mark.parametrize(
    "reactions", [{"white_check_mark": ["U0OTHER"]}, {"fast_forward": ["U0ME"]}, {}]
)
def test_without_learner_check_mark_only_reminds(lab_root, httpx_mock, reactions):
    seed(lab_root, open_record())
    mock_gate(httpx_mock, reactions)
    mock_post(httpx_mock, ts="100.2")
    code, summary, _ = daily(lab_root, "--target", "lab", now=on(1))
    assert code == 0 and summary["status"] == "REMINDED"
    assert summary["daily"]["hint_included"] is False
    reply = bodies(httpx_mock, POST)[0]
    assert reply["thread_ts"] == "100.1" and reply["text"] == "아직 해결 전: 시나리오 d-easy"
    [record] = posted(lab_root)["daily"]
    assert record["outcome"] == "open" and record["reminders"] == ["2026-10-27"]


def test_second_run_same_day_does_not_remind_again(lab_root, httpx_mock):
    seed(lab_root, open_record())
    for _ in range(2):
        mock_gate(httpx_mock, {})
    mock_post(httpx_mock, ts="100.2")
    daily(lab_root, "--target", "lab", now=on(1))
    code, summary, _ = daily(lab_root, "--target", "lab", now=on(1))
    assert code == 0 and summary["status"] == "ALREADY_REMINDED"
    assert len(httpx_mock.get_requests(url=POST)) == 1


def test_reminder_carries_hint_one_from_day_three(lab_root, httpx_mock):
    seed(lab_root, open_record())
    mock_gate(httpx_mock, {})
    mock_post(httpx_mock, ts="100.2")
    _, summary, _ = daily(lab_root, "--target", "lab", now=on(3))
    assert summary["daily"]["hint_included"] is True
    raw = json.dumps(bodies(httpx_mock, POST)[0], ensure_ascii=False)
    assert hint_sentinel("d-easy", 1) in raw and hint_sentinel("d-easy", 2) not in raw
    assert "게시 후 3일" in raw
    progress = ProgressStore(lab_root / "data" / "progress.json").load()
    assert not [e for e in progress.events if e.type == "hint_opened"]


def test_open_mission_reminds_without_hint(lab_root, httpx_mock):
    seed(lab_root, open_record(main="c-one", day=1, main_kind="mission"))
    mock_gate(httpx_mock, {})
    mock_post(httpx_mock, ts="100.2")
    _, summary, _ = daily(lab_root, "--target", "lab", now=on(5))
    assert summary["daily"]["hint_included"] is False


def test_solved_progress_without_check_mark_still_reminds(lab_root, httpx_mock):
    seed(lab_root, open_record())
    store = ProgressStore(lab_root / "data" / "progress.json")
    for event in progress_of(
        ev("scenario_started", "d-easy", 0, attempt=1),
        ev("scenario_solved", "d-easy", 1, attempt=1, hints_used=0),
    ).events:
        store.append(event)
    mock_gate(httpx_mock, {})
    mock_post(httpx_mock, ts="100.2")
    _, summary, _ = daily(lab_root, "--target", "lab", now=on(1))
    assert summary["status"] == "REMINDED"


def test_missing_message_reposts_same_problem(lab_root, httpx_mock):
    seed(lab_root, open_record())
    httpx_mock.add_response(url=API + "auth.test", json={"ok": True, "user_id": "U0BOT"})
    httpx_mock.add_response(url=REACTIONS, json={"ok": False, "error": "message_not_found"})
    mock_post(httpx_mock, ts="300.1")
    httpx_mock.add_response(url=TEST_HOOK, text="ok")
    code, summary, _ = daily(lab_root, "--target", "lab", now=on(1))
    assert code == 0 and summary["status"] == "REPOSTED"
    repost = bodies(httpx_mock, POST)[0]
    assert "thread_ts" not in repost and "다시 올려요" in json.dumps(repost, ensure_ascii=False)
    [record] = posted(lab_root)["daily"]
    assert record["ts"] == "300.1" and record["outcome"] == "open" and record["reposted_at"]
    assert bodies(httpx_mock, TEST_HOOK)[0]["text"] == "⚠️ troubleshoot-lab WARNING"


def test_reaction_lookup_failure_keeps_record(lab_root, httpx_mock):
    before = seed(lab_root, open_record())
    httpx_mock.add_response(url=API + "auth.test", json={"ok": True, "user_id": "U0BOT"})
    for _ in range(3):
        httpx_mock.add_response(url=REACTIONS, status_code=503)
    httpx_mock.add_response(url=TEST_HOOK, text="ok")
    code, summary, _ = daily(lab_root, "--target", "lab", now=on(1))
    assert code == 1 and summary["status"] == "POST_FAILED"
    assert (lab_root / "data" / "posted.json").read_bytes() == before
    assert bodies(httpx_mock, TEST_HOOK)[0]["text"] == "⚠️ troubleshoot-lab POST_FAILED"


def test_next_post_failure_after_solve_keeps_record(lab_root, httpx_mock):
    before = seed(lab_root, open_record())
    mock_gate(httpx_mock, {"white_check_mark": ["U0ME"]})
    httpx_mock.add_response(url=POST, json={"ok": False, "error": "not_in_channel"})
    httpx_mock.add_response(url=TEST_HOOK, text="ok")
    code, summary, _ = daily(lab_root, "--target", "lab", now=on(1))
    assert code == 1 and summary["error"] == "chat.postMessage: not_in_channel"
    assert (lab_root / "data" / "posted.json").read_bytes() == before
    alert = json.dumps(bodies(httpx_mock, TEST_HOOK)[0], ensure_ascii=False)
    assert "not_in_channel" in alert


def test_records_from_before_the_gate_read_as_finished(lab_root, httpx_mock):
    legacy = {k: v for k, v in open_record(date_kst="2026-10-25").items() if k in LEGACY_FIELDS}
    seed(lab_root, legacy)
    mock_post(httpx_mock)
    _, summary, _ = daily(lab_root, "--target", "lab")
    assert summary["status"] == "POSTED" and summary["daily"]["day"] == 3
    assert not httpx_mock.get_requests(url=REACTIONS)


def test_second_run_same_day_is_already_posted(lab_root, httpx_mock):
    mock_post(httpx_mock, ts="100.1")
    daily(lab_root, "--target", "lab")
    code, summary, _ = daily(lab_root, "--target", "lab")
    assert code == 0 and summary["status"] == "ALREADY_POSTED"
    assert len(httpx_mock.get_requests()) == 1


# --- preview targets --------------------------------------------------------------------


def test_test_target_previews_next_problem_and_never_records(lab_root, httpx_mock):
    httpx_mock.add_response(url=TEST_HOOK, text="ok")
    daily(lab_root, "--target", "test")
    assert bodies(httpx_mock, TEST_HOOK)[0]["text"].startswith("[TEST] ")
    assert posted(lab_root)["daily"] == []


def test_test_target_with_open_problem_previews_reminder(lab_root, httpx_mock):
    before = seed(lab_root, open_record())
    httpx_mock.add_response(url=TEST_HOOK, text="ok")
    _, summary, _ = daily(lab_root, "--target", "test", now=on(1))
    assert summary["status"] == "REMINDED"
    assert bodies(httpx_mock, TEST_HOOK)[0]["text"] == "[TEST] 아직 해결 전: 시나리오 d-easy"
    assert not httpx_mock.get_requests(url=REACTIONS)
    assert (lab_root / "data" / "posted.json").read_bytes() == before


def test_dry_run_prints_and_sends_nothing(lab_root, httpx_mock):
    code, summary, output = daily(lab_root, "--dry-run", "--force", env={})
    assert code == 0 and "개념 미션" in output and "✅를 달아 주세요" in output
    assert httpx_mock.get_requests() == []


# --- failures and configuration ---------------------------------------------------------


def test_post_failure_alerts_test_channel(lab_root, httpx_mock):
    httpx_mock.add_response(url=POST, json={"ok": False, "error": "channel_not_found"})
    httpx_mock.add_response(url=TEST_HOOK, text="ok")
    code, summary, _ = daily(lab_root, "--target", "lab")
    assert code == 1 and summary["status"] == "POST_FAILED"
    assert bodies(httpx_mock, TEST_HOOK)[0]["text"] == "⚠️ troubleshoot-lab POST_FAILED"
    assert posted(lab_root)["daily"] == []


def test_invalid_scenario_warns_but_still_posts(lab_root, httpx_mock):
    write_scenario(lab_root, {"id": "broken", "title": "t"}, field_dir="linux", scripts=False)
    httpx_mock.add_response(url=TEST_HOOK, text="ok")
    mock_post(httpx_mock)
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
        *((["--target", "lab"], {k: v for k, v in ENV.items() if k != gone}) for gone in ENV),
        (["--target", "test"], {}),
        (["--target", "lab", "--force"], ENV),
        (["--target", "lab", "--today", "2026-11-01"], ENV),
    ],
)
def test_usage_errors_exit_2(lab_root, args, env, capsys):
    from troubleshoot_lab.cli import main

    assert main(["daily", *args], lab_root=lab_root, environ=env, out=io.StringIO()) == 2
    err = capsys.readouterr().err
    assert "hooks.slack.com" not in err and TOKEN not in err


def test_secrets_never_logged(lab_root, httpx_mock, caplog):
    seed(lab_root, open_record())
    mock_gate(httpx_mock, {"white_check_mark": ["U0ME"]})
    mock_post(httpx_mock)
    with caplog.at_level(logging.DEBUG):
        daily(lab_root, "--target", "lab", now=on(1))
    assert TOKEN not in caplog.text and "TESTTESTTEST" not in caplog.text


# --- weekly -----------------------------------------------------------------------------


def test_sunday_kst_posts_daily_then_weekly_through_the_bot(lab_root, httpx_mock):
    mock_post(httpx_mock, ts="100.1")
    mock_post(httpx_mock, ts="100.2")
    code, summary, _ = daily(lab_root, "--target", "lab", now=SATURDAY_UTC_SUNDAY_KST)
    assert code == 0 and summary["weekly"]["status"] == "POSTED"
    sent = bodies(httpx_mock, POST)
    assert sent[0]["text"].startswith("📚") and sent[1]["text"].startswith("📊")
    assert all(b["channel"] == "C0LAB" for b in sent)
    record = posted(lab_root)
    assert record["daily"][0]["date_kst"] == "2026-11-01"
    assert record["weekly"][0]["week_start_kst"] == "2026-10-26"


def test_post_modes_and_weekly_dedup(lab_root, httpx_mock):
    httpx_mock.add_response(url=TEST_HOOK, text="ok", is_reusable=True)
    _, summary, _ = daily(lab_root, "--target", "test")
    assert summary["weekly"] is None
    _, summary, _ = daily(lab_root, "--target", "test", "--post", "weekly")
    assert summary["daily"] is None and summary["weekly"]["status"] == "POSTED"
    mock_post(httpx_mock, ts="100.1")
    daily(lab_root, "--target", "lab", "--post", "weekly", now=MONDAY)
    mock_post(httpx_mock, ts="100.2")
    _, summary, _ = daily(lab_root, "--target", "lab", now=SATURDAY_UTC_SUNDAY_KST)
    assert (
        summary["daily"]["status"] == "POSTED" and summary["weekly"]["status"] == "ALREADY_POSTED"
    )


def test_sunday_with_open_problem_reminds_and_sends_weekly(lab_root, httpx_mock):
    seed(lab_root, open_record(date_kst="2026-10-29"))
    mock_gate(httpx_mock, {})
    mock_post(httpx_mock, ts="100.2")  # reminder
    mock_post(httpx_mock, ts="100.3")  # weekly
    code, summary, _ = daily(lab_root, "--target", "lab", now=SATURDAY_UTC_SUNDAY_KST)
    assert code == 0 and summary["status"] == "REMINDED"
    assert summary["weekly"]["status"] == "POSTED"
    reminder, weekly = bodies(httpx_mock, POST)
    assert reminder["thread_ts"] == "100.1" and weekly["text"].startswith("📊")
    raw = json.dumps(weekly, ensure_ascii=False)
    assert "미해결로 멈춘 날 1일" in raw and "*지금 열린 문제* 시나리오 d-easy (게시 후 3일)" in raw
