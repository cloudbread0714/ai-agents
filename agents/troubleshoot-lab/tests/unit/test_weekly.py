import shutil
from datetime import UTC, date, datetime
from pathlib import Path

from tl_support import NOW, ev, make_catalog, progress_of, scenario_spec
from troubleshoot_lab.catalog import load_catalog
from troubleshoot_lab.messages import build_weekly
from troubleshoot_lab.models import DailyPost, Posted, Progress
from troubleshoot_lab.weekly import summarize, week_start

SUNDAY_RUN = datetime(2026, 10, 31, 23, 40, tzinfo=UTC)  # Sunday 11/01 08:40 KST
TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "report.md"


def _setup(tmp_path):
    repo = tmp_path / "repo"
    lab = repo / "agents" / "troubleshoot-lab"
    lab.mkdir(parents=True)
    make_catalog(
        lab,
        scenarios=[
            scenario_spec("n1", fields=["network"], no="1"),
            scenario_spec("l1", fields=["linux"], no="2"),
            scenario_spec("w1", fields=["webserver"], no="3"),
        ],
    )
    (lab / "templates").mkdir()
    shutil.copy(TEMPLATE, lab / "templates" / "report.md")
    return repo, load_catalog(lab)


def _at(day, hour):
    return datetime(2026, 10, day, hour, tzinfo=UTC)


def _e(type_, sid, ts, **kw):
    return ev(type_, sid, 0, **kw).model_copy(update={"ts": ts})


def test_week_start_is_monday_kst():
    assert week_start(SUNDAY_RUN) == date(2026, 10, 26)
    assert week_start(datetime(2026, 11, 1, 23, 30, tzinfo=UTC)) == date(2026, 11, 2)


def test_counts_reports_answers_pending_and_weak_field(tmp_path):
    repo, cat = _setup(tmp_path)
    report = "agents/troubleshoot-lab/docs/reports/2026-10-26-n1-1.md"
    (repo / report).parent.mkdir(parents=True)
    (repo / report).write_text("done")
    progress = progress_of(
        _e("scenario_started", "n1", _at(25, 14), attempt=1),  # last week
        _e("scenario_started", "n1", _at(26, 1), attempt=2),
        _e("hint_opened", "n1", _at(26, 2), attempt=2, level=1),
        _e("hint_opened", "n1", _at(26, 3), attempt=2, level=2),
        _e("scenario_solved", "n1", _at(26, 4), attempt=2, hints_used=2),
        _e(
            "report_completed",
            "n1",
            _at(26, 5),
            attempt=2,
            report=report.replace("-1.md", "-2.md"),
            answered=1,
        ),
        _e("scenario_started", "l1", _at(27, 1), attempt=1),
        _e("hint_opened", "l1", _at(27, 2), attempt=1, level=1),
        _e("scenario_gave_up", "l1", _at(27, 3), attempt=1, hints_used=1),
    )
    posted = Posted(
        daily=[
            DailyPost(
                date_kst=date(2026, 10, 27),
                kind="day",
                day=3,
                main_kind="scenario",
                main_id="w1",
                posted_at=NOW,
            )
        ]
    )
    s = summarize(cat, progress, posted, SUNDAY_RUN, repo)
    assert (s.solved, s.gave_up, s.hints, s.reviewed, s.answered) == (1, 1, 3, 1, 1)
    assert s.progress_label == "3/21일 차"
    # n1 attempt 2 report path does not exist → still pending; l1 gave up without a report
    assert s.pending == [("시나리오 n1", 2), ("시나리오 l1", 1)]
    # network: 2 hints; linux: 1 hint + 2×give-up = 3
    assert s.weak_field == "linux"
    assert s.backlog == 1  # w1 posted, unsolved
    assert s.next_topic == "주제 4"
    assert not s.empty


def test_weak_field_ties_and_zero(tmp_path):
    repo, cat = _setup(tmp_path)
    tie = progress_of(
        _e("scenario_started", "w1", _at(26, 1), attempt=1),
        _e("scenario_reset", "w1", _at(26, 2), attempt=1, was_active=True),  # webserver 2
        _e("scenario_started", "n1", _at(27, 1), attempt=1),
        _e("scenario_gave_up", "n1", _at(27, 2), attempt=1, hints_used=0),  # network 2
    )
    assert summarize(cat, tie, Posted(), SUNDAY_RUN, repo).weak_field == "network"  # ① before ③
    clean = progress_of(
        _e("scenario_started", "n1", _at(26, 1), attempt=1),
        _e("scenario_solved", "n1", _at(26, 2), attempt=1, hints_used=0),
    )
    assert summarize(cat, clean, Posted(), SUNDAY_RUN, repo).weak_field is None


def test_empty_week_message(tmp_path):
    repo, cat = _setup(tmp_path)
    s = summarize(cat, Progress(), Posted(), SUNDAY_RUN, repo)
    assert s.empty and s.next_topic == "주제 1"
    payload = build_weekly(s, test_mode=True)
    text = "\n".join(b["text"]["text"] for b in payload["blocks"] if "text" in b)
    assert payload["text"] == "[TEST] 📊 이번 주 학습 요약 (10/26~11/01)"
    assert "*진행* 0/21일 차" in text and "이번 주에는 기록이 없어요" in text
    assert "*다음 주제* 주제 1" in text


def test_weekly_message_lines(tmp_path):
    repo, cat = _setup(tmp_path)
    progress = progress_of(
        _e("scenario_started", "l1", _at(27, 1), attempt=1),
        _e("hint_opened", "l1", _at(27, 2), attempt=1, level=1),
        _e("scenario_gave_up", "l1", _at(27, 3), attempt=1, hints_used=1),
    )
    text = "\n".join(
        b["text"]["text"]
        for b in build_weekly(summarize(cat, progress, Posted(), SUNDAY_RUN, repo))["blocks"]
        if "text" in b
    )
    assert "*해결* 0개   *포기* 1개   *힌트* 1회" in text
    assert "*회고* 완료 0개 · 면접 질문 답변 0개" in text
    assert "*회고 대기*\n• 시나리오 l1 (시도 1)" in text
    assert "*약한 분야* ② 리눅스 서버" in text
    assert "*밀린 문제* 0개" in text
