"""Solve gate for the daily problem (004 research R6–R7): pure decisions, no Slack calls.

Only ✅ on the open problem's message moves the plan on. Who added it matters: the learner
(``SLACK_USER_ID``) or the bot itself (``/lab-check``'s automatic reaction). Every other
reaction, including ⏭️, is ignored.
"""

from __future__ import annotations

from collections.abc import Mapping, Set
from datetime import date
from typing import Literal

from troubleshoot_lab.catalog import Catalog
from troubleshoot_lab.models import DailyPost

CHECK_MARKS = frozenset({"white_check_mark", "heavy_check_mark"})
HINT_AFTER_DAYS = 3

Verdict = Literal["solved", "unsolved"]


def judge(reactions: Mapping[str, Set[str]], user_id: str, bot_id: str) -> Verdict:
    counted = {user_id, bot_id}
    for name in CHECK_MARKS:
        if reactions.get(name, set()) & counted:
            return "solved"
    return "unsolved"


def days_open(post: DailyPost, today: date) -> int:
    return (today - post.date_kst).days


def reminder_due(post: DailyPost, today: date) -> bool:
    """At most one reminder per problem per KST day, and never on the day it was posted."""
    return today > post.date_kst and today not in post.reminders


def hint_due(post: DailyPost, today: date) -> bool:
    return days_open(post, today) >= HINT_AFTER_DAYS


def hint_source(post: DailyPost, catalog: Catalog) -> str | None:
    """The scenario whose hint 1 the reminder carries: the main item, else the second one.
    Missions have no hints."""
    for item_id in (post.main_id, post.second_id):
        if item_id and item_id in catalog.scenarios and catalog.hints.get(item_id):
            return item_id
    return None
