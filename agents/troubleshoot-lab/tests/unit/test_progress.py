import json

import pytest
from pydantic import ValidationError

from tl_support import ev, measured, metrics, progress_of
from troubleshoot_lab import progress as prog
from troubleshoot_lab.models import Event, Metric


def test_append_keeps_time_order_and_writes_v2(store):
    store.append(ev("mission_completed", "m-one", 5))
    store.append(ev("mission_completed", "deleted-later", 1))
    data = json.loads(store.path.read_text())
    assert data["version"] == 2
    assert [e["id"] for e in data["events"]] == ["deleted-later", "m-one"]
    assert "level" not in data["events"][0]


def test_v1_empty_upgrades_and_v1_with_events_errors(tmp_path):
    path = tmp_path / "p.json"
    path.write_text('{"version": 1, "events": []}')
    assert prog.ProgressStore(path).load().version == 2
    path.write_text(
        '{"version": 1, "events": [{"ts": "2026-10-26T00:00:00Z", "type": "x", "id": "a"}]}'
    )
    with pytest.raises(prog.ProgressFormatError):
        prog.ProgressStore(path).load()


def test_event_field_requirements():
    with pytest.raises(ValidationError):
        ev("scenario_started", "s")  # attempt
    with pytest.raises(ValidationError):
        ev("hint_opened", "s", attempt=1)
    with pytest.raises(ValidationError):
        ev("measured", "s", attempt=1, phase="baseline")
    with pytest.raises(ValidationError):
        ev("measured", "s", attempt=1, phase="baseline", metrics={"avg_ms": {"value": 1}})
    with pytest.raises(ValidationError):
        ev("report_completed", "s", attempt=1, report="elsewhere/x.md", answered=1)
    with pytest.raises(ValidationError):
        Metric(value=1.0, status="unavailable")
    with pytest.raises(ValidationError):
        Metric()
    with pytest.raises(ValidationError):
        Event.model_validate({"ts": "2026-10-26T00:00:00", "type": "mission_completed", "id": "s"})


def test_stage_machine_and_measurements():
    p = progress_of(
        ev("scenario_started", "a", 0, attempt=1),
        measured("a", 1, 1, "baseline", avg_ms=10.0),
        ev("fault_injected", "a", 2, attempt=1),
        measured("a", 3, 1, "fault", avg_ms=500.0),
        ev("hint_opened", "a", 4, attempt=1, level=1),
        ev("scenario_solved", "a", 5, attempt=1, hints_used=1),
        measured("a", 6, 1, "after", avg_ms=11.0),
        ev(
            "report_completed",
            "a",
            7,
            attempt=1,
            report="agents/troubleshoot-lab/docs/reports/x.md",
            answered=2,
        ),
    )
    (a,) = prog.attempts(p)
    assert a.stage == "solved" and a.end_type == "solved"
    assert {k: v.metrics["avg_ms"].value for k, v in a.measurements.items()} == {
        "baseline": 10.0,
        "fault": 500.0,
        "after": 11.0,
    }
    assert a.hints == 1 and a.reviewed and a.answered == 2


@pytest.mark.parametrize(
    "events,stage",
    [
        ([ev("scenario_started", "a", 0, attempt=1)], "started"),
        (
            [ev("scenario_started", "a", 0, attempt=1), measured("a", 1, 1, "baseline")],
            "baseline_ok",
        ),
        (
            [
                ev("scenario_started", "a", 0, attempt=1),
                measured("a", 1, 1, "baseline"),
                ev("fault_injected", "a", 2, attempt=1),
            ],
            "injected",
        ),
        (
            [
                ev("scenario_started", "a", 0, attempt=1),
                measured("a", 1, 1, "baseline"),
                ev("fault_injected", "a", 2, attempt=1),
                measured("a", 3, 1, "fault"),
            ],
            "fault_ok",
        ),
    ],
)
def test_stages(events, stage):
    assert prog.attempts(progress_of(*events))[0].stage == stage


def test_attempt_numbers_active_and_reset():
    p = progress_of(
        ev("scenario_started", "a", 0, attempt=1),
        ev("scenario_reset", "a", 1, attempt=1, was_active=True),
        ev("scenario_started", "a", 2, attempt=2),
        ev("hint_opened", "a", 3, attempt=2, level=1),
    )
    assert [a.end_type for a in prog.attempts(p)] == ["reset", None]
    assert prog.active_scenario(p) == "a"
    assert prog.active_attempt(p).attempt == 2
    assert prog.next_attempt_no(p, "a") == 3
    assert prog.hints_in_active(p, "a") == 1
    assert prog.next_attempt_no(p, "b") == 1


def test_status_rules():
    p = progress_of(
        ev("scenario_started", "a", 0, attempt=1),
        ev("scenario_solved", "a", 1, attempt=1, hints_used=0),
        ev("scenario_started", "a", 2, attempt=2),
        ev("scenario_gave_up", "a", 3, attempt=2, hints_used=1),
        ev("scenario_started", "b", 4, attempt=1),
        ev("scenario_gave_up", "b", 5, attempt=1, hints_used=3),
        ev("scenario_started", "c", 6, attempt=1),
    )
    assert prog.scenario_status(p, "a") == "solved"
    assert prog.scenario_status(p, "b") == "gave_up"
    assert prog.scenario_status(p, "c") == "pending"
    assert prog.scenario_status(p, "d") == "new"
    assert prog.scenario_status(p, "d", posted_ids={"d"}) == "pending"
    assert [a.scenario_id for a in prog.finished_attempts(p)] == ["a", "a", "b"]


def test_metrics_helper_shapes():
    m = metrics(avg_ms=1.5, p95_ms="not_applicable")
    assert m["avg_ms"] == {"value": 1.5} and m["p95_ms"] == {"status": "not_applicable"}
    assert m["cpu_max_pct"] == {"status": "unavailable"}
