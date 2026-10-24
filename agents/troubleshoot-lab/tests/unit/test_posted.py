from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from tl_support import NOW
from troubleshoot_lab import posted as posted_mod
from troubleshoot_lab.models import DailyPost, Posted, WeeklyPost


def _daily(day, main="s", kind="day", n=1, second=None, at=NOW, main_kind="scenario"):
    return DailyPost(date_kst=day, kind=kind, day=n if kind == "day" else None, main_kind=main_kind,
                     main_id=main, second_id=second, posted_at=at)


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
        DailyPost(date_kst=date(2026, 10, 26), kind="day", main_kind="scenario", main_id="s", posted_at=NOW)
    with pytest.raises(ValidationError):
        DailyPost(date_kst=date(2026, 10, 26), kind="catchup", day=3, main_kind="scenario", main_id="s",
                  posted_at=NOW)
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
