import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from news_digest import history
from news_digest.models import History, PostRecord

SCHEMA = Path(__file__).parents[4] / "specs/001-news-daily-digest/contracts/history.schema.json"


def _record(i: int, posted_at: datetime, category="infra") -> PostRecord:
    return PostRecord(
        article_id=f"{i:016x}",
        url=f"https://example.com/{i}",
        title=f"title {i}",
        title_ko=f"제목 {i}",
        category=category,
        source="s",
        posted_at=posted_at,
        posted_date_kst=(posted_at + timedelta(hours=9)).date(),
    )


NOW = datetime(2026, 10, 25, 23, 0, tzinfo=UTC)


def test_missing_file_is_empty_history(tmp_path):
    assert history.load(tmp_path / "nope.json") == History()


def test_round_trip_matches_contract_schema(tmp_path):
    path = tmp_path / "data" / "posted.json"
    h = History(posts=[_record(1, NOW - timedelta(days=1))])
    history.save(path, h, now=NOW)
    raw = json.loads(path.read_text())
    assert raw["version"] == 1
    schema = json.loads(SCHEMA.read_text())
    record_keys = set(schema["properties"]["posts"]["items"]["required"])
    assert set(raw["posts"][0]) == record_keys
    assert history.load(path) == h


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / "posted.json"
    history.save(path, History(), now=NOW)
    assert [p.name for p in tmp_path.iterdir()] == ["posted.json"]


def test_save_prunes_entries_older_than_365_days(tmp_path):
    path = tmp_path / "posted.json"
    old = _record(1, NOW - timedelta(days=366))
    keep = _record(2, NOW - timedelta(days=364))
    history.save(path, History(posts=[old, keep]), now=NOW)
    assert [p.article_id for p in history.load(path).posts] == [keep.article_id]


def test_queries():
    h = History(
        posts=[
            _record(1, NOW - timedelta(days=2), "ai_agent"),
            _record(2, NOW - timedelta(days=1), "infra"),
            _record(3, NOW - timedelta(hours=1), "infra"),  # 2026-10-26 KST
        ]
    )
    assert history.posted_ids(h) == {f"{i:016x}" for i in (1, 2, 3)}
    assert history.posted_today(h, date(2026, 10, 26)) is True
    assert history.posted_today(h, date(2026, 10, 27)) is False
    assert history.recent_categories(h, 2) == ["infra", "infra"]
    assert history.recent_categories(h, 5) == ["ai_agent", "infra", "infra"]


def test_append_keeps_chronological_order():
    h = History(posts=[_record(2, NOW)])
    h = history.append(h, _record(1, NOW - timedelta(days=1)))
    assert [p.article_id for p in h.posts] == [f"{1:016x}", f"{2:016x}"]


def test_invalid_article_id_rejected():
    with pytest.raises(ValueError):
        _record(1, NOW).model_copy(update={}).model_validate(
            {**_record(1, NOW).model_dump(), "article_id": "XYZ"}
        )
