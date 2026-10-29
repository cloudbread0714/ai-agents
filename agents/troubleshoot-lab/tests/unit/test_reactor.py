import json

import pytest

from tl_support import ev, progress_of
from troubleshoot_lab.catalog import load_catalog
from troubleshoot_lab.models import Progress
from troubleshoot_lab.reactor import Reactor

TOKEN = "xoxb-test-secret"
ADD = "https://slack.com/api/reactions.add"
SOLVED_D = progress_of(
    ev("scenario_started", "d-easy", 0, attempt=1),
    ev("scenario_solved", "d-easy", 1, attempt=1, hints_used=0),
)


def _seed(lab_root, main="d-easy", second=None, outcome="open", main_kind="scenario"):
    record = {
        "date_kst": "2026-11-02",
        "kind": "day",
        "day": 3,
        "main_kind": main_kind,
        "main_id": main,
        "second_id": second,
        "posted_at": "2026-11-01T23:40:00Z",
        "channel": "C0LAB",
        "ts": "100.1",
        "outcome": outcome,
        "resolved_at": "2026-11-03T23:40:00Z" if outcome == "solved" else None,
    }
    path = lab_root / "data" / "posted.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 2, "daily": [record], "weekly": []}))


def _react(lab_root, item, progress, env=None):
    reactor = Reactor(lab_root, {"SLACK_BOT_TOKEN": TOKEN} if env is None else env, base_delay=0)
    return reactor.after_done(item, progress, load_catalog(lab_root))


def test_marks_open_problem_when_its_only_item_is_solved(lab_root, httpx_mock):
    _seed(lab_root)
    httpx_mock.add_response(url=ADD, json={"ok": True})
    result = _react(lab_root, "d-easy", SOLVED_D)
    assert result.status == "added" and "✅를 달았어요" in result.message
    request = httpx_mock.get_request(url=ADD)
    assert json.loads(request.content) == {
        "channel": "C0LAB",
        "timestamp": "100.1",
        "name": "white_check_mark",
    }
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"


def test_already_reacted(lab_root, httpx_mock):
    _seed(lab_root)
    httpx_mock.add_response(url=ADD, json={"ok": False, "error": "already_reacted"})
    assert _react(lab_root, "d-easy", SOLVED_D).status == "already"


def test_partial_when_second_item_remains(lab_root, httpx_mock):
    _seed(lab_root, second="w-easy")
    result = _react(lab_root, "d-easy", SOLVED_D)
    assert result.status == "partial" and "시나리오 w-easy" in result.message
    assert httpx_mock.get_requests() == []


def test_mission_counts_when_completed(lab_root, httpx_mock):
    _seed(lab_root, main="c-one", main_kind="mission")
    httpx_mock.add_response(url=ADD, json={"ok": True})
    done = progress_of(ev("mission_completed", "c-one", 0))
    assert _react(lab_root, "c-one", done).status == "added"


def test_other_item_is_not_open(lab_root, httpx_mock):
    _seed(lab_root, main="w-easy")
    result = _react(lab_root, "d-easy", SOLVED_D)
    assert (result.status, result.message) == ("not_open", None)
    assert httpx_mock.get_requests() == []


@pytest.mark.parametrize("state", ["missing", "solved"])
def test_no_open_problem_locally_asks_for_pull(lab_root, httpx_mock, state):
    if state == "solved":
        _seed(lab_root, outcome="solved")
    result = _react(lab_root, "d-easy", SOLVED_D)
    assert result.status == "not_open" and "git pull" in result.message


def test_no_token(lab_root, httpx_mock):
    _seed(lab_root)
    result = _react(lab_root, "d-easy", SOLVED_D, env={})
    assert result.status == "no_config" and "직접 달아 주세요" in result.message
    assert httpx_mock.get_requests() == []


def test_slack_failure_is_reported_not_raised(lab_root, httpx_mock):
    _seed(lab_root)
    for _ in range(3):
        httpx_mock.add_response(url=ADD, status_code=503)
    result = _react(lab_root, "d-easy", SOLVED_D)
    assert result.status == "failed" and "HTTP 503" in result.message
    assert TOKEN not in result.message


def test_broken_record_is_reported_not_raised(lab_root):
    path = lab_root / "data" / "posted.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert _react(lab_root, "d-easy", Progress()).status == "failed"
