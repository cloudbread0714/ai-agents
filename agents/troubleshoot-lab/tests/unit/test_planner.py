from datetime import date, timedelta

import pytest

from tl_support import NOW, ev, make_catalog, progress_of, scenario_spec, write_plan
from troubleshoot_lab.catalog import load_catalog
from troubleshoot_lab.models import DailyPost, Posted, Progress
from troubleshoot_lab.planner import backlog, plan_today

TODAY = date(2026, 10, 26)
IDS = ["s1", "s2", "s3", "s4", "s5"]


@pytest.fixture
def cat(tmp_path):
    root = make_catalog(
        tmp_path, scenarios=[scenario_spec(s, no=str(i)) for i, s in enumerate(IDS, 1)]
    )
    days = {
        1: {"items": ["c-one"]},
        2: {"items": ["s1"]},
        3: {"items": ["s2", "s3"]},
        4: {"items": ["s1"]},
        7: {"pool": ["s1", "s2", "s3", "s4"]},
    }
    write_plan(root, days, extras=["s5"], fill=lambda d: "s4")
    return load_catalog(root)


def post(d: date, kind="day", day=None, main="s1", main_kind="scenario", second=None):
    return DailyPost(
        date_kst=d,
        kind=kind,
        day=day,
        main_kind=main_kind,
        main_id=main,
        second_id=second,
        posted_at=NOW,
    )


def posted(*posts):
    return Posted(daily=list(posts))


def ago(n):
    return TODAY - timedelta(days=n)


def test_first_post_is_day_one_concept(cat):
    pick = plan_today(cat, Progress(), Posted(), TODAY)
    assert (pick.kind, pick.day, pick.main_id, pick.main_kind) == ("day", 1, "c-one", "mission")
    assert pick.minutes == 60


def test_next_day_after_last_day_post_with_second_item(cat):
    p = posted(
        post(ago(2), day=1, main="c-one", main_kind="mission"), post(ago(1), day=2, main="s1")
    )
    pick = plan_today(cat, Progress(), p, TODAY)
    assert (pick.day, pick.main_id, pick.second_id) == (3, "s2", "s3")
    assert pick.backlog == ["s1"]  # posted, unsolved


def test_catchup_when_three_unsolved(cat):
    p = posted(
        post(ago(3), day=2, main="s1"),
        post(ago(2), day=3, main="s2", second="s3"),
        post(ago(1), day=4, main="s4"),
    )
    pick = plan_today(cat, Progress(), p, TODAY)
    assert pick.kind == "catchup" and pick.main_id == "s1"  # oldest backlog
    assert pick.backlog == ["s2", "s3", "s4"]  # main excluded, at most 3 shown


def test_solved_and_gave_up_leave_the_backlog(cat):
    p = posted(post(ago(3), day=2, main="s1"), post(ago(2), day=3, main="s2", second="s3"))
    prog = progress_of(
        ev("scenario_started", "s1", 0, attempt=1),
        ev("scenario_solved", "s1", 1, attempt=1, hints_used=0),
        ev("scenario_started", "s3", 2, attempt=1),
        ev("scenario_gave_up", "s3", 3, attempt=1, hints_used=3),
    )
    assert backlog(cat, prog, p, TODAY) == ["s2"]


def test_review_flag_when_main_already_solved(cat):
    p = posted(*(post(ago(10 - i), day=i, main="s4") for i in (1, 2, 3)))
    prog = progress_of(
        ev("scenario_started", "s1", 0, attempt=1),
        ev("scenario_solved", "s1", 1, attempt=1, hints_used=0),
        ev("scenario_started", "s4", 2, attempt=1),
        ev("scenario_solved", "s4", 3, attempt=1, hints_used=0),
    )
    pick = plan_today(cat, prog, p, TODAY)
    assert (pick.day, pick.main_id, pick.review_flag) == (4, "s1", True)
    assert pick.plan_day.practice == "실습 4"


def test_composite_pool_order(cat):
    base = [post(ago(10 - i), day=i, main="s4") for i in range(1, 7)]  # s4 posted, unsolved
    solved = [
        ev("scenario_started", "s4", 0, attempt=1),
        ev("scenario_solved", "s4", 1, attempt=1, hints_used=0),
    ]
    # never-posted unsolved first: s1 (curriculum 1)
    pick = plan_today(cat, progress_of(*solved), posted(*base), TODAY)
    assert (pick.day, pick.composite, pick.main_id, pick.second_id) == (7, True, "s1", None)

    # all posted: unsolved oldest-posted wins
    more = [
        post(ago(30), kind="catchup", main="s2"),
        post(ago(20), kind="catchup", main="s1"),
        post(ago(25), kind="catchup", main="s3"),
    ]
    pick = plan_today(cat, progress_of(*solved), posted(*base, *more), TODAY)
    assert pick.main_id == "s2"

    # everything finished: gave up beats solved, then most hints
    done = [
        ev("scenario_started", "s1", 0, attempt=1),
        ev("scenario_solved", "s1", 1, attempt=1, hints_used=2),
        ev("scenario_started", "s2", 2, attempt=1),
        ev("scenario_solved", "s2", 3, attempt=1, hints_used=0),
        ev("scenario_started", "s3", 4, attempt=1),
        ev("scenario_gave_up", "s3", 5, attempt=1, hints_used=1),
    ]
    pick = plan_today(cat, progress_of(*solved, *done), posted(*base), TODAY)
    assert pick.main_id == "s3"


def test_extras_then_review(cat):
    days = [post(ago(30 - i), day=i, main="s4") for i in range(1, 22)]
    pick = plan_today(cat, Progress(), posted(*days), TODAY)
    assert (pick.kind, pick.main_id, pick.extra_index) == ("extra", "s5", 1)

    prog = progress_of(
        ev("scenario_started", "s4", 0, attempt=1),
        ev("scenario_solved", "s4", 1, attempt=1, hints_used=3),
        ev("scenario_started", "s5", 2, attempt=1),
        ev("scenario_gave_up", "s5", 3, attempt=1, hints_used=0),
    )
    p = posted(*days, post(ago(1), kind="extra", main="s5"))
    pick = plan_today(cat, prog, p, TODAY)
    assert pick.kind == "review" and pick.main_id == "s4"  # yesterday's s5 avoided


def test_minutes_skip_completed_warmups(cat):
    p = posted(post(ago(1), day=1, main="c-one", main_kind="mission"))
    assert plan_today(cat, Progress(), p, TODAY).minutes == 60  # 45 + 15 warmup
    done = progress_of(ev("mission_completed", "m-one", 0))
    assert plan_today(cat, done, p, TODAY).minutes == 45


def test_invalid_plan_or_nothing_to_pick(tmp_path):
    root = make_catalog(tmp_path, scenarios=[scenario_spec("a")], plan=False)
    assert plan_today(load_catalog(root), Progress(), Posted(), TODAY) is None


def test_deterministic(cat):
    p = posted(post(ago(2), day=2, main="s1"), post(ago(1), day=3, main="s2", second="s3"))
    first = plan_today(cat, Progress(), p, TODAY)
    assert all(plan_today(cat, Progress(), p, TODAY) == first for _ in range(10))
