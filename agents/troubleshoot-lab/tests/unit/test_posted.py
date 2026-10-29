from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from tl_support import NOW
from troubleshoot_lab import posted as posted_mod
from troubleshoot_lab.models import DailyPost, Posted, WeeklyPost


def _daily(day, main="s", kind="day", n=1, second=None, at=NOW, main_kind="scenario"):
    return DailyPost(
        date_kst=day,
        kind=kind,
        day=n if kind == "day" else None,
        main_kind=main_kind,
        main_id=main,
        second_id=second,
        posted_at=at,
    )


def test_v1_empty_upgrades_and_v1_with_records_errors(tmp_path):
    path = tmp_path / "posted.json"
    path.write_text('{"version": 1, "daily": [], "weekly": []}')
    assert posted_mod.load(path).version == 2
    path.write_text('{"version": 1, "daily": [{"date_kst": "2026-10-26"}], "weekly": []}')
    with pytest.raises(posted_mod.PostedFormatError):
        posted_mod.load(path)


def test_rules():
    with pytest.raises(ValidationError):
        Posted(daily=[_daily(date(2026, 10, 26)), _daily(date(2026, 10, 26), "t")])
    with pytest.raises(ValidationError):
        DailyPost(
            date_kst=date(2026, 10, 26),
            kind="day",
            main_kind="scenario",
            main_id="s",
            posted_at=NOW,
        )
    with pytest.raises(ValidationError):
        DailyPost(
            date_kst=date(2026, 10, 26),
            kind="catchup",
            day=3,
            main_kind="scenario",
            main_id="s",
            posted_at=NOW,
        )
    with pytest.raises(ValidationError):
        Posted(weekly=[WeeklyPost(week_start_kst=date(2026, 10, 26), posted_at=NOW)] * 2)


def test_save_prunes_old_records_atomically(tmp_path):
    path = tmp_path / "posted.json"
    old = _daily(date(2025, 10, 1), "old", at=NOW - timedelta(days=400))
    posted_mod.save(path, Posted(daily=[old, _daily(date(2026, 10, 26))]), now=NOW)
    assert [d.main_id for d in posted_mod.load(path).daily] == ["s"]
    assert [p.name for p in tmp_path.iterdir()] == ["posted.json"]


def test_lookups():
    posted = Posted(
        daily=[
            _daily(date(2026, 10, 20), "c-one", n=1, main_kind="mission"),
            _daily(date(2026, 10, 21), "a", n=2, second="b"),
            _daily(date(2026, 10, 22), "c", kind="catchup"),
            _daily(date(2026, 10, 24), "a", n=4),
        ],
        weekly=[WeeklyPost(week_start_kst=date(2026, 10, 19), posted_at=NOW)],
    )
    today = date(2026, 10, 26)
    assert posted_mod.posted_on(posted, date(2026, 10, 22)).main_id == "c"
    assert posted_mod.previous_daily(posted, today).main_id == "a"
    assert posted_mod.last_day(posted, today) == 4
    assert posted_mod.last_day(posted, date(2026, 10, 22)) == 2
    assert posted_mod.last_posted(posted, "b") == date(2026, 10, 21)
    assert posted_mod.last_posted(posted, "a", date(2026, 10, 24)) == date(2026, 10, 21)
    assert posted_mod.posted_ids(posted) == {"a", "b", "c"}  # missions are not scenarios
    assert posted_mod.posted_mains(posted) == {"c-one", "a", "c"}
    assert posted_mod.weekly_posted(posted, date(2026, 10, 19))


def _gated(day, *, outcome="open", resolved_at=None, reminders=(), **kw):
    return _daily(day, **kw).model_copy(
        update={
            "channel": "C0LAB",
            "ts": "1.2",
            "outcome": outcome,
            "resolved_at": resolved_at,
            "reminders": list(reminders),
        }
    )


def test_records_without_message_location_read_as_finished(tmp_path):
    path = tmp_path / "posted.json"
    path.write_text(
        '{"version": 2, "daily": [{"date_kst": "2026-10-27", "kind": "day", "day": 2,'
        ' "main_kind": "scenario", "main_id": "s", "second_id": null,'
        ' "posted_at": "2026-10-27T02:24:59Z"}], "weekly": []}'
    )
    post = posted_mod.load(path).daily[0]
    assert (post.channel, post.ts, post.outcome, post.resolved_at, post.reposted_at) == (
        None,
        None,
        None,
        None,
        None,
    )
    assert post.reminders == []
    assert posted_mod.open_post(posted_mod.load(path)) is None


def _validate(**fields):
    base = {
        "date_kst": date(2026, 11, 2),
        "kind": "day",
        "day": 3,
        "main_kind": "scenario",
        "main_id": "s",
        "posted_at": NOW,
    }
    return DailyPost.model_validate({**base, **fields})


@pytest.mark.parametrize(
    "fields",
    [
        {"channel": "C0LAB"},  # channel and ts are set together
        {"ts": "1.2"},
        {"outcome": "open"},  # outcome needs a message location
        {"channel": "C0LAB", "ts": "1.2", "outcome": "solved"},  # solved ⇔ resolved_at
        {"channel": "C0LAB", "ts": "1.2", "outcome": "open", "resolved_at": NOW},
        {"reminders": [date(2026, 11, 4), date(2026, 11, 3)]},  # ascending
        {"reminders": [date(2026, 11, 3), date(2026, 11, 3)]},  # unique
        {"reminders": [date(2026, 11, 2)]},  # after date_kst
    ],
)
def test_gated_field_rules(fields):
    with pytest.raises(ValidationError):
        _validate(**fields)


def test_gated_fields_valid():
    post = _validate(
        channel="C0LAB",
        ts="1.2",
        outcome="open",
        reminders=[date(2026, 11, 3), date(2026, 11, 4)],
    )
    assert post.outcome == "open"


def test_at_most_one_open_post():
    with pytest.raises(ValidationError):
        Posted(daily=[_gated(date(2026, 11, 2)), _gated(date(2026, 11, 3), main="t")])


def test_open_post_lookup():
    solved = _gated(date(2026, 11, 2), outcome="solved", resolved_at=NOW)
    current = _gated(date(2026, 11, 3), main="t")
    assert posted_mod.open_post(Posted(daily=[solved, current])).main_id == "t"
    assert posted_mod.open_post(Posted(daily=[solved])) is None


def test_save_keeps_open_post_past_retention(tmp_path):
    path = tmp_path / "posted.json"
    stale_open = _gated(date(2025, 10, 1), main="stuck", at=NOW - timedelta(days=400))
    stale_done = _daily(date(2025, 10, 2), "old", at=NOW - timedelta(days=400))
    posted_mod.save(path, Posted(daily=[stale_open, stale_done]), now=NOW)
    assert [d.main_id for d in posted_mod.load(path).daily] == ["stuck"]
