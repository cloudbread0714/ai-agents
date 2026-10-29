from tl_support import (
    hint_sentinel,
    interview_sentinel,
    metrics,
    solution_sentinel,
    start_hint_sentinel,
    tag_sentinel,
)
from troubleshoot_lab.guard import EnvNotReady, SandboxError
from troubleshoot_lab.learn import NOT_SOLVED


def _types(store):
    return [(e.type, e.id, e.phase) for e in store.load().events]


def _complete(learner, mission_id):
    assert learner.start(mission_id).outcome == "ok"
    assert learner.check().outcome == "mission_step_passed"
    assert learner.check("tok").outcome == "mission_completed"


def _ready(learner, scenario="w-easy"):
    """Warmups done, scenario started, baseline measured, fault injected and measured."""
    _complete(learner, "m-one")
    assert learner.start(scenario).outcome == "ok"
    assert learner.measure().outcome == "measured"
    assert learner.inject().outcome == "ok"
    assert learner.measure().outcome == "measured"


def test_locked_scenario_lists_missing_warmups_and_runs_nothing(learner, runner):
    out = learner.start("d-easy")
    assert (out.outcome, out.exit_code) == ("locked", 4)
    assert out.extra["missing_warmups"] == ["m-one", "m-two"]
    assert runner.calls == []


def test_mission_steps_answers_and_completion(learner, runner, store):
    start = learner.start("m-one")
    assert start.outcome == "ok" and "단계 1/2" in start.text
    assert runner.dirty == ["compose"]
    assert learner.check().outcome == "mission_step_passed"
    missing = learner.check()
    assert (missing.outcome, missing.exit_code) == ("failed", 1) and "토큰을 입력" in missing.text
    runner.set("m-one", "verify.sh", 1)
    assert learner.check("bad").outcome == "failed"
    runner.set("m-one", "verify.sh", 0)
    done = learner.check("tok")
    assert done.outcome == "mission_completed"
    assert runner.calls[-1] == ("environment", "restore.sh", ("compose",))
    assert _types(store) == [("mission_completed", "m-one", None)]


def test_start_restores_opens_attempt_and_does_not_inject(learner, runner, store):
    _complete(learner, "m-one")
    runner.calls.clear()
    out = learner.start("w-easy")
    assert out.outcome == "ok" and out.extra == {"attempt": 1, "stage": "started"}
    assert runner.scripts() == ["environment:restore.sh"]  # no inject.sh yet
    assert "1단계" in out.text and "/lab-measure" in out.text and "증상 w-easy" in out.text
    for leaked in (
        hint_sentinel("w-easy", 1),
        solution_sentinel("w-easy"),
        tag_sentinel("w-easy"),
        start_hint_sentinel("w-easy"),
        interview_sentinel("w-easy"),
    ):
        assert leaked not in out.text
    assert _types(store)[-1] == ("scenario_started", "w-easy", None)


def test_inject_requires_baseline_measurement(learner, runner, measurer, store):
    _complete(learner, "m-one")
    learner.start("w-easy")
    out = learner.inject()
    assert (out.outcome, out.exit_code) == ("need_measure", 4)
    assert "w-easy:inject.sh" not in runner.scripts()

    m = learner.measure()
    assert m.outcome == "measured" and m.extra["phase"] == "baseline"
    assert measurer.calls == [("w-easy", 1, "baseline")]
    assert "/lab-inject" in m.text

    out = learner.inject()
    assert out.outcome == "ok" and out.extra["stage"] == "injected"
    assert runner.dirty[-1] == "compose"
    assert start_hint_sentinel("w-easy") in out.text  # start_hint is shown after injection
    assert learner.inject().outcome == "busy"


def test_inject_failure_records_nothing(learner, runner, store):
    _complete(learner, "m-one")
    learner.start("w-easy")
    learner.measure()
    runner.set("w-easy", "inject.sh", 1)
    assert learner.inject().outcome == "failed"
    assert ("fault_injected", "w-easy", None) not in _types(store)


def test_check_requires_fault_measurement(learner, runner):
    _complete(learner, "m-one")
    learner.start("w-easy")
    assert learner.check().outcome == "need_measure"
    learner.measure()
    learner.inject()
    out = learner.check()
    assert (out.outcome, out.exit_code) == ("need_measure", 4)
    assert "w-easy:verify.sh" not in runner.scripts()


def test_fault_measurement_compares_to_baseline(learner, measurer):
    _complete(learner, "m-one")
    learner.start("w-easy")
    measurer.by_phase["baseline"] = metrics(avg_ms=10.0, error_rate=0.0)
    learner.measure()
    learner.inject()
    measurer.by_phase["fault"] = metrics(avg_ms=40.0, error_rate=1.0, p95_ms="not_applicable")
    out = learner.measure()
    assert out.extra["phase"] == "fault"
    assert "| 평균 응답 시간 | 40.0 ms | ×4.0 |" in out.text
    assert "| p95 응답 시간 | 해당 없음 | — |" in out.text
    assert "/lab-exec" in out.text and "/lab-check" in out.text


def test_measure_failure_records_nothing_and_skip_records_reason(learner, measurer, store):
    _complete(learner, "m-one")
    learner.start("w-easy")
    measurer.fail = True
    out = learner.measure()
    assert (out.outcome, out.exit_code) == ("failed", 1) and "--skip" in out.text
    assert not any(e.type == "measured" for e in store.load().events)
    out = learner.measure("k6 이미지 다운로드 실패")
    assert out.outcome == "skipped"
    event = store.load().events[-1]
    assert event.skip_reason == "k6 이미지 다운로드 실패"
    assert {m.status for m in event.metrics.values()} == {"skipped"}
    assert learner.inject().outcome == "ok"  # a skipped baseline still unlocks step 2


def test_hints_only_after_injection_and_in_order(learner, store):
    _complete(learner, "m-one")
    learner.start("w-easy")
    assert learner.hint().outcome == "none"
    learner.measure()
    learner.inject()
    texts = [learner.hint().text for _ in range(3)]
    assert all(hint_sentinel("w-easy", n) in t for n, t in zip((1, 2, 3), texts, strict=True))
    assert learner.hint().outcome == "none"
    assert [e.level for e in store.load().events if e.type == "hint_opened"] == [1, 2, 3]


def test_check_failure_reveals_nothing(learner, runner):
    _ready(learner)
    runner.set("w-easy", "verify.sh", 1)
    out = learner.check()
    assert (out.outcome, out.exit_code, out.text) == ("failed", 1, NOT_SOLVED)


def test_check_success_records_solve_then_auto_after_measurement(learner, measurer, store):
    _ready(learner)
    learner.hint()
    out = learner.check()
    assert out.outcome == "solved" and out.sync_suggested
    assert measurer.calls[-1] == ("w-easy", 1, "after")
    types = _types(store)
    assert types[-2:] == [("scenario_solved", "w-easy", None), ("measured", "w-easy", "after")]
    assert solution_sentinel("w-easy") in out.text and "/lab-report" in out.text
    assert "해결 후" in out.text


def test_after_measurement_failure_keeps_the_solve(learner, measurer, store):
    _ready(learner)
    measurer.fail = True
    out = learner.check()
    assert out.outcome == "solved" and "/lab-measure" in out.text
    assert _types(store)[-1] == ("scenario_solved", "w-easy", None)
    measurer.fail = False
    assert learner.measure().extra["phase"] == "after"  # can re-measure after solving


def test_giveup_then_report_flow(learner, lab_root, repo_root, store):
    assert learner.giveup().outcome == "none"
    _complete(learner, "m-one")
    learner.start("w-easy")
    out = learner.giveup()
    assert out.outcome == "gave_up" and out.sync_suggested and "/lab-report" in out.text
    created = learner.report()
    assert created.outcome == "created"
    path = repo_root / created.extra["report"]
    assert path.exists() and "결과 포기" in path.read_text()
    assert learner.report().outcome == "exists"


def test_report_done_checks_sections_then_records(learner, repo_root, store):
    _ready(learner)
    learner.check()
    created = learner.report()
    path = repo_root / created.extra["report"]
    incomplete = learner.report(done=True)
    assert (incomplete.outcome, incomplete.exit_code) == ("incomplete", 1)
    assert "증상" in incomplete.extra["missing"]
    text = path.read_text()
    for section in ("증상", "원인", "분석 과정", "해결 방법", "재발 방지"):
        text = text.replace(f"## {section}\n", f"## {section}\n썼어요\n", 1)
    text = text.replace(
        f"### Q1. {interview_sentinel('w-easy')}\n", f"### Q1. {interview_sentinel('w-easy')}\n답\n"
    )
    path.write_text(text)
    done = learner.report(done=True)
    assert done.outcome == "reviewed" and done.sync_suggested
    event = store.load().events[-1]
    assert (event.type, event.answered, event.report) == (
        "report_completed",
        1,
        created.extra["report"],
    )
    assert learner.report(done=True).outcome == "reviewed"  # idempotent, no second event
    assert sum(e.type == "report_completed" for e in store.load().events) == 1


def test_report_without_finished_attempt(learner):
    assert learner.report().outcome == "none"


def test_one_active_item_across_missions_and_scenarios(learner):
    _complete(learner, "m-one")
    learner.start("w-easy")
    assert learner.start("m-two").outcome == "busy"
    learner.reset()
    learner.start("m-two")
    assert learner.start("w-easy").outcome == "busy"


def test_reset_records_and_keeps_measurements(learner, runner, store):
    _ready(learner)
    assert learner.reset().outcome == "ok"
    events = store.load().events
    assert (events[-1].type, events[-1].attempt) == ("scenario_reset", 1)
    assert sum(e.type == "measured" for e in events) == 2
    assert "측정 기록과 보고서는 그대로" in learner.reset("w-easy").text
    out = learner.start("w-easy")
    assert out.extra["attempt"] == 2


def test_guard_errors_map_to_exit_codes(learner):
    def raise_(exc):
        def g(env):
            raise exc

        return g

    learner.guard = raise_(EnvNotReady("make up 먼저"))
    assert (learner.start("m-one").exit_code, learner.measure().exit_code) == (5, 4)
    learner.guard = raise_(SandboxError("원격"))
    assert learner.start("m-one").exit_code == 3


def test_list_shows_fields_stage_and_pending_reports(learner):
    _complete(learner, "m-one")
    learner.start("w-easy")
    text = learner.list().text
    assert "▶ 진행 중: 시나리오 w-easy (w-easy) · 1단계 정상 상태 측정" in text
    assert "## ① 네트워크" in text and "## ② 리눅스 서버" in text
    assert "[개념 60분] c-one" in text and "[#2 초급 45분] w-easy" in text
    learner.giveup()
    assert "📝 보고서 대기: w-easy(시도 1)" in learner.list().text
    for sid in ("d-easy", "w-easy", "d-mid"):
        assert tag_sentinel(sid) not in text and hint_sentinel(sid, 1) not in text


class _FakeReactor:
    def __init__(self, status="added", message="Slack 오늘의 문제에 ✅를 달았어요."):
        self.calls: list[str] = []
        self.status, self.message = status, message

    def after_done(self, item_id, progress, catalog):
        from troubleshoot_lab.reactor import ReactionResult

        self.calls.append(item_id)
        return ReactionResult(self.status, self.message)


def test_solve_marks_slack_and_reports_it(learner, store):
    learner.reactor = _FakeReactor()
    _ready(learner)
    out = learner.check()
    assert out.outcome == "solved" and out.exit_code == 0 and out.sync_suggested
    assert learner.reactor.calls == ["m-one", "w-easy"]  # warmup completion, then the solve
    assert out.text.rstrip().endswith("Slack 오늘의 문제에 ✅를 달았어요.")
    assert out.result()["slack_reaction"] == "added"


def test_mission_completion_marks_slack(learner):
    learner.reactor = _FakeReactor(status="partial", message="남은 항목이 있어요")
    learner.start("m-one")
    learner.check()
    out = learner.check("tok")
    assert out.outcome == "mission_completed" and out.result()["slack_reaction"] == "partial"
    assert out.text.rstrip().endswith("남은 항목이 있어요")


def test_reaction_failure_changes_nothing_else(learner, store):
    learner.reactor = _FakeReactor(status="failed", message="✅ 자동 반응을 달지 못했어요")
    _ready(learner)
    out = learner.check()
    assert (out.outcome, out.exit_code, out.sync_suggested) == ("solved", 0, True)
    assert store.load().events[-2].type == "scenario_solved"


def test_failed_check_and_giveup_do_not_touch_slack(learner, runner):
    learner.reactor = _FakeReactor()
    _ready(learner)
    learner.reactor.calls.clear()
    runner.set("w-easy", "verify.sh", 1)
    failed = learner.check()
    assert failed.outcome == "failed" and "slack_reaction" not in failed.result()
    learner.giveup()
    assert learner.reactor.calls == []


def test_without_reactor_result_has_no_slack_field(learner):
    _ready(learner)
    assert "slack_reaction" not in learner.check().result()
