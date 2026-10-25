import json
from datetime import date

from tl_support import (
    ev,
    hint_sentinel,
    interview_sentinel,
    progress_of,
    solution_sentinel,
    start_hint_sentinel,
    tag_sentinel,
)
from troubleshoot_lab.catalog import load_catalog
from troubleshoot_lab.messages import build_daily
from troubleshoot_lab.models import Progress
from troubleshoot_lab.planner import DayPick

DAY = date(2026, 10, 26)  # Monday


def _text(payload):
    parts = [payload["text"]]
    for b in payload["blocks"]:
        if "text" in b:
            parts.append(b["text"]["text"])
        parts += [el["text"] for el in b.get("elements", [])]
    return "\n".join(parts)


def _day_pick(cat, day, main, **kw):
    return DayPick(
        kind="day",
        day=day,
        plan_day=cat.plan.get(day),
        main_id=main,
        main_kind="scenario" if main in cat.scenarios else "mission",
        **kw,
    )


def test_scenario_day_message(lab_root):
    cat = load_catalog(lab_root)
    pick = _day_pick(cat, 2, "d-easy", minutes=60, second_id="w-easy", backlog=["d-mid"])
    payload = build_daily(pick, cat, Progress(), DAY)
    text = _text(payload)
    assert payload["text"] == "📚 2일 차 · 1주 차: 주제 2"
    assert "⏱ 예상 60분 (60~90분 기준)" in text and "*오늘 실습* 실습 2" in text
    assert "*🧪 주 문제* 시나리오 d-easy" in text
    assert "*난이도* 초급   *분야* ② 리눅스 서버   *#*3" in text
    assert "*증상*\n증상 d-easy" in text
    assert "`/lab-start d-easy`  → 정상 상태 측정 → 장애 재현" in text
    assert "• ⬜ 미션 m-one — `/lab-start m-one`" in text
    assert "*시간이 남으면* 시나리오 w-easy — `/lab-start w-easy`" in text
    assert "*밀린 문제*\n• 시나리오 d-mid — `/lab-start d-mid`" in text
    assert "2026-10-26 (월)" in text


def test_concept_day_message(lab_root):
    cat = load_catalog(lab_root)
    text = _text(build_daily(_day_pick(cat, 1, "c-one", minutes=60), cat, Progress(), DAY))
    assert "*🧭 개념 미션* 미션 c-one — `/lab-start c-one`" in text
    assert "*워밍업*" not in text


def test_time_lines(lab_root):
    cat = load_catalog(lab_root)
    long = _text(build_daily(_day_pick(cat, 2, "d-easy", minutes=95), cat, Progress(), DAY))
    short = _text(build_daily(_day_pick(cat, 2, "d-easy", minutes=45), cat, Progress(), DAY))
    assert "90분을 넘어요" in long and "남는 시간에는" in short


def test_review_catchup_extra_and_composite_headers(lab_root):
    cat = load_catalog(lab_root)
    review = _text(
        build_daily(_day_pick(cat, 4, "d-easy", minutes=60, review_flag=True), cat, Progress(), DAY)
    )
    assert "· 복습" in review and "이번에는 이 관점으로: 실습 4" in review
    for kind, extra, header in [
        ("catchup", {}, "🔁 따라잡기 날"),
        ("review", {}, "🔁 복습 문제"),
        ("extra", {"extra_index": 1}, "🧩 심화 문제 1/0"),
    ]:
        pick = DayPick(kind=kind, main_id="d-mid", main_kind="scenario", minutes=60, **extra)
        assert build_daily(pick, cat, Progress(), DAY)["text"] == header
    comp = DayPick(
        kind="day",
        day=7,
        plan_day=cat.plan.get(7),
        main_id="d-mid",
        main_kind="scenario",
        minutes=60,
        composite=True,
    )
    assert build_daily(comp, cat, Progress(), DAY)["text"].endswith("(종합: 후보 중 1개)")


def test_warmups_done_and_in_progress_warning(lab_root):
    cat = load_catalog(lab_root)
    prog = progress_of(
        ev("mission_completed", "m-one", 0),
        ev("mission_completed", "m-two", 1),
        ev("scenario_started", "w-easy", 2, attempt=1),
    )
    pick = _day_pick(cat, 2, "d-easy", minutes=30)
    text = _text(build_daily(pick, cat, prog, DAY, test_mode=True))
    assert text.startswith("[TEST] 📚")
    assert "• ✅ 미션 m-one — 완료됨" in text and "바로 시작하세요" in text
    assert "⚠️ 진행 중인 시나리오(시나리오 w-easy)가 있어요" in text


def test_no_hidden_text_anywhere_in_payload(lab_root):
    cat = load_catalog(lab_root)
    for sid in cat.scenarios:
        raw = json.dumps(
            build_daily(_day_pick(cat, 2, sid, minutes=60), cat, Progress(), DAY),
            ensure_ascii=False,
        )
        for leaked in (
            *[hint_sentinel(sid, n) for n in (1, 2, 3)],
            solution_sentinel(sid),
            tag_sentinel(sid),
            start_hint_sentinel(sid),
            interview_sentinel(sid),
            "/api/items",  # measure spec
        ):
            assert leaked not in raw


def test_mrkdwn_escaped(tmp_path):
    from tl_support import make_catalog, scenario_spec

    spec = {**scenario_spec("esc"), "symptom": "<!channel> & <b>"}
    cat = load_catalog(make_catalog(tmp_path, scenarios=[spec]))
    text = _text(build_daily(_day_pick(cat, 2, "esc", minutes=60), cat, Progress(), DAY))
    assert "&lt;!channel&gt; &amp; &lt;b&gt;" in text
