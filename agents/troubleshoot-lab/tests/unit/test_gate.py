from datetime import date

import pytest

from tl_support import NOW, make_catalog, scenario_spec
from troubleshoot_lab import gate
from troubleshoot_lab.catalog import load_catalog
from troubleshoot_lab.models import DailyPost

POSTED = date(2026, 11, 2)


def _post(main="s1", main_kind="scenario", second=None, reminders=()):
    return DailyPost(
        date_kst=POSTED,
        kind="day",
        day=3,
        main_kind=main_kind,
        main_id=main,
        second_id=second,
        posted_at=NOW,
        channel="C0LAB",
        ts="1.2",
        outcome="open",
        reminders=list(reminders),
    )


@pytest.mark.parametrize(
    ("reactions", "verdict"),
    [
        ({"white_check_mark": {"U0ME"}}, "solved"),
        ({"heavy_check_mark": {"U0ME"}}, "solved"),
        ({"white_check_mark": {"U0BOT"}}, "solved"),
        ({"white_check_mark": {"U0OTHER"}}, "unsolved"),
        ({"fast_forward": {"U0ME"}}, "unsolved"),
        ({"eyes": {"U0ME"}, "white_check_mark": set()}, "unsolved"),
        ({}, "unsolved"),
    ],
)
def test_judge(reactions, verdict):
    assert gate.judge(reactions, "U0ME", "U0BOT") == verdict


def test_reminder_due_once_per_day_and_not_on_post_day():
    assert not gate.reminder_due(_post(), POSTED)
    assert gate.reminder_due(_post(), date(2026, 11, 3))
    assert not gate.reminder_due(_post(reminders=[date(2026, 11, 3)]), date(2026, 11, 3))
    assert gate.reminder_due(_post(reminders=[date(2026, 11, 3)]), date(2026, 11, 4))


def test_hint_due_from_three_days():
    assert not gate.hint_due(_post(), date(2026, 11, 4))  # 2 days
    assert gate.hint_due(_post(), date(2026, 11, 5))  # 3 days: Mon → Thu


def test_hint_source(tmp_path):
    root = make_catalog(tmp_path, scenarios=[scenario_spec("s1")])
    cat = load_catalog(root)
    assert gate.hint_source(_post("s1"), cat) == "s1"
    assert gate.hint_source(_post("c-one", "mission", second="s1"), cat) == "s1"
    assert gate.hint_source(_post("c-one", "mission"), cat) is None
