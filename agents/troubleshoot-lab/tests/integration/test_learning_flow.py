"""US1 end to end: the six steps on a #3-like scenario with fake runner and measurer."""

from tl_support import metrics


def test_six_steps_produce_events_and_a_report(learner, measurer, store, repo_root):
    # warmups (step 0)
    for mission in ("m-one", "m-two"):
        learner.start(mission)
        learner.check()
        learner.check("tok")

    measurer.by_phase = {
        "baseline": metrics(
            avg_ms=12.0,
            p95_ms=30.0,
            rps=200.0,
            error_rate=0.0,
            requests=4000,
            cpu_avg_pct=8.0,
            cpu_max_pct=15.0,
            mem_max_mib=60.0,
        ),
        "fault": metrics(
            avg_ms="not_applicable",
            p95_ms="not_applicable",
            rps=50.0,
            error_rate=1.0,
            requests=1000,
            cpu_avg_pct=1.0,
            cpu_max_pct=2.0,
            mem_max_mib=58.0,
        ),
        "after": metrics(
            avg_ms=13.0,
            p95_ms=31.0,
            rps=195.0,
            error_rate=0.0,
            requests=3900,
            cpu_avg_pct=8.5,
            cpu_max_pct=16.0,
            mem_max_mib=61.0,
        ),
    }
    assert learner.start("d-easy").outcome == "ok"  # opens attempt 1
    assert learner.measure().extra["phase"] == "baseline"  # 1
    assert learner.inject().outcome == "ok"  # 2
    assert learner.measure().extra["phase"] == "fault"  # 3
    assert learner.hint().outcome == "ok"  # 4
    assert learner.check().outcome == "solved"  # 5 (+ after)
    created = learner.report()  # 6
    path = repo_root / created.extra["report"]
    text = path.read_text()
    assert "| 평균 응답 시간 (ms) | 12.0 | 해당 없음 | 13.0 |" in text
    assert "| 오류율 (%) | 0.0 | 100.0 | 0.0 |" in text

    for section in ("증상", "원인", "분석 과정", "해결 방법", "재발 방지"):
        text = text.replace(f"## {section}\n", f"## {section}\n작성함\n", 1)
    text = text.replace("<!-- 직접 작성 -->", "답변")
    path.write_text(text)
    assert learner.report(done=True).outcome == "reviewed"

    events = [(e.type, e.phase) for e in store.load().events if e.id == "d-easy"]
    assert events == [
        ("scenario_started", None),
        ("measured", "baseline"),
        ("fault_injected", None),
        ("measured", "fault"),
        ("hint_opened", None),
        ("scenario_solved", None),
        ("measured", "after"),
        ("report_completed", None),
    ]
