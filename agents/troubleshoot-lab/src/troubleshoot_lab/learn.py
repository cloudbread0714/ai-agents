"""The six-step learning loop behind the /lab-* commands (research R22, contracts/cli.md).

1 measure baseline → 2 inject → 3 measure fault + diagnose → 4 hints → 5 check (auto after
measurement) → 6 report. Every function returns an ``Outcome``: Korean text for the learner,
a machine-readable result (the ``LAB_RESULT`` line) and an exit code.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from troubleshoot_lab import progress as prog
from troubleshoot_lab import report as rep
from troubleshoot_lab.catalog import Catalog
from troubleshoot_lab.diag import Diagnoser
from troubleshoot_lab.guard import EnvNotReady, SandboxError, check_for, restore_mode
from troubleshoot_lab.measure import MeasureError, format_table, skipped, strip_display
from troubleshoot_lab.models import (
    DIFFICULTY_LABEL,
    DIFFICULTY_RANK,
    FIELD_LABEL,
    FIELDS,
    PHASE_LABEL,
    Event,
    Mission,
    MissionStep,
    Progress,
    Scenario,
)
from troubleshoot_lab.progress import Attempt, ProgressStore
from troubleshoot_lab.reactor import Reactor
from troubleshoot_lab.runner import Runner
from troubleshoot_lab.session import Session

NOT_SOLVED = "아직 해결되지 않았어요. 증상을 다시 확인해 보세요."
STEPS = "1 정상 측정 → 2 장애 재현 → 3 관찰 → 4 분석 → 5 해결 → 6 보고서"
STAGE_LABEL = {
    "started": "1단계 정상 상태 측정",
    "baseline_ok": "2단계 장애 재현",
    "injected": "3단계 장애 상태 측정",
    "fault_ok": "3~5단계 관찰·분석·해결",
}


class MeasurerLike(Protocol):
    def run(self, scenario: Scenario, attempt: int, phase: str) -> dict: ...


@dataclass
class Outcome:
    text: str
    command: str
    outcome: str
    exit_code: int = 0
    kind: str | None = None
    id: str | None = None
    sync_suggested: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def result(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "kind": self.kind,
            "id": self.id,
            "outcome": self.outcome,
            "sync_suggested": self.sync_suggested,
            **self.extra,
        }


Guard = Callable[[str], None]


class Learner:
    def __init__(
        self,
        catalog: Catalog,
        store: ProgressStore,
        session: Session,
        runner: Runner,
        *,
        guard: Guard,
        measurer: MeasurerLike,
        diagnoser: Diagnoser | None = None,
        reactor: Reactor | None = None,
        repo_root: Path | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.catalog = catalog
        self.store = store
        self.session = session
        self.runner = runner
        self.guard = guard
        self.measurer = measurer
        self.diagnoser = diagnoser
        self.reactor = reactor
        self.repo_root = repo_root or catalog.root.parents[1]
        self.now = now

    # --- helpers --------------------------------------------------------------------

    def _progress(self) -> Progress:
        return self.store.load()

    def _record(self, type_: str, item_id: str, **fields: Any) -> None:
        self.store.append(Event(ts=self.now(), type=type_, id=item_id, **fields))

    def _dir(self, item_id: str) -> Path:
        return self.catalog.paths[item_id]

    def _active(self, progress: Progress) -> tuple[str, str] | None:
        """("scenario"|"mission", id) for the single item in progress (FR-025)."""
        if sid := prog.active_scenario(progress):
            return "scenario", sid
        if mission := self.session.get():
            if mission.id in self.catalog.missions:
                return "mission", mission.id
            self.session.clear()
        return None

    def _react(self, item_id: str) -> tuple[list[str], dict[str, Any]]:
        """Mark today's Slack problem ✅ once ``item_id`` finishes it (004 FR-013). Returns the
        lines to append and the ``LAB_RESULT`` field; both empty without a reactor."""
        if self.reactor is None:
            return [], {}
        reaction = self.reactor.after_done(item_id, self._progress(), self.catalog)
        lines = ["", reaction.message] if reaction.message else []
        return lines, {"slack_reaction": reaction.status}

    def _title(self, item_id: str) -> str:
        item = self.catalog.get(item_id)
        return item.title if item else item_id

    def _guarded(self, command: str, fn: Callable[[], Outcome]) -> Outcome:
        try:
            return fn()
        except EnvNotReady as exc:
            return Outcome(str(exc), command, "not_ready", 5)
        except SandboxError as exc:
            return Outcome(str(exc), command, "refused", 3)

    def _scenario_out(
        self, text, command, outcome, code=0, *, attempt: Attempt | None = None, **kw
    ):
        extra = kw.pop("extra", {})
        if attempt is not None:
            extra = {"attempt": attempt.attempt, "stage": attempt.stage, **extra}
        sid = attempt.scenario_id if attempt else kw.pop("id", None)
        return Outcome(text, command, outcome, code, kind="scenario", id=sid, extra=extra, **kw)

    def _active_attempt(self) -> Attempt | None:
        return prog.active_attempt(self._progress())

    # --- list -----------------------------------------------------------------------

    def list(self) -> Outcome:
        progress = self._progress()
        active = self._active(progress)
        lines: list[str] = []
        if active:
            label = ""
            if active[0] == "scenario":
                a = prog.active_attempt(progress)
                label = f" · {STAGE_LABEL.get(a.stage, a.stage)}"
            lines += [f"▶ 진행 중: {self._title(active[1])} ({active[1]}){label}", ""]
        pending = [
            a for a in prog.finished_attempts(progress) if rep.status(a, self.repo_root) != "done"
        ]
        if pending:
            lines.append(
                "📝 보고서 대기: "
                + ", ".join(f"{a.scenario_id}(시도 {a.attempt})" for a in pending)
            )
            lines.append("")
        for f in FIELDS:
            missions = [m for m in self.catalog.missions.values() if m.field == f]
            scenarios = sorted(
                (s for s in self.catalog.scenarios.values() if s.field == f),
                key=lambda s: (DIFFICULTY_RANK[s.difficulty], s.id),
            )
            if not missions and not scenarios:
                continue
            lines.append(f"## {FIELD_LABEL[f]}")
            for m in missions:
                mark = "✅" if prog.mission_done(progress, m.id) else "⬜"
                kind = "개념" if m.kind == "concept" else "워밍업"
                lines.append(f"  {mark} [{kind} {m.minutes}분] {m.id} — {m.title}")
            for s in scenarios:
                lines.append(
                    f"  {self._badge(progress, s, active)} [#{s.curriculum_no} "
                    f"{DIFFICULTY_LABEL[s.difficulty]} {s.minutes}분] {s.id} — {s.title}"
                )
                lines.append(f"      증상: {s.symptom.strip()}")
            lines.append("")
        if self.catalog.errors:
            lines.append("⚠️ 유효하지 않아 제외된 항목")
            lines += [f"  - {e}" for e in self.catalog.errors]
        lines.append("시작: /lab-start <id>")
        return Outcome("\n".join(lines).rstrip(), "list", "ok")

    def _missing_warmups(self, progress: Progress, scenario: Scenario) -> list[str]:
        return [w for w in scenario.warmups if not prog.mission_done(progress, w)]

    def _badge(self, progress: Progress, s: Scenario, active) -> str:
        status = prog.scenario_status(progress, s.id)
        if active == ("scenario", s.id):
            return "▶ 진행 중"
        if status == "solved":
            return "✅ 해결"
        if status == "gave_up":
            return "🏳️ 포기"
        missing = self._missing_warmups(progress, s)
        return f"🔒 잠김(남은 워밍업: {', '.join(missing)})" if missing else "🔓 열림"

    # --- start ----------------------------------------------------------------------

    def start(self, item_id: str) -> Outcome:
        return self._guarded("start", lambda: self._start(item_id))

    def _start(self, item_id: str) -> Outcome:
        kind = self.catalog.kind(item_id)
        if kind is None:
            err = self.catalog.error_for(item_id)
            text = (
                f"'{item_id}'은(는) 유효하지 않아 사용할 수 없어요: {err.message}"
                if err
                else f"'{item_id}'을(를) 찾을 수 없어요. /lab-list 로 목록을 확인하세요."
            )
            return Outcome(text, "start", "unknown", 2, id=item_id)
        progress = self._progress()
        if active := self._active(progress):
            return Outcome(
                f"이미 진행 중인 항목이 있어요: {self._title(active[1])} ({active[1]}).\n"
                "끝내거나 /lab-reset 으로 원복한 뒤 시작하세요.",
                "start",
                "busy",
                4,
                kind=kind,
                id=item_id,
            )
        if kind == "mission":
            return self._start_mission(self.catalog.missions[item_id])
        return self._start_scenario(progress, self.catalog.scenarios[item_id])

    def _start_mission(self, mission: Mission) -> Outcome:
        self.guard(mission.env)
        self.runner.mark_dirty(mission.env)
        if self.runner.run(mission.id, self._dir(mission.id), "setup.sh") != 0:
            return Outcome(
                "미션을 준비하지 못했어요. /lab-reset 후 다시 시도하세요.",
                "start",
                "failed",
                1,
                kind="mission",
                id=mission.id,
            )
        self.session.set(mission.id, 0)
        kind = "개념 미션" if mission.kind == "concept" else "워밍업 미션"
        text = "\n".join(
            [
                f"🧭 {kind}: {mission.title} (예상 {mission.minutes}분)",
                "학습 목표",
                *[f"  • {g}" for g in mission.goals],
                "",
                _step_text(mission, 0),
            ]
        )
        return Outcome(text, "start", "ok", kind="mission", id=mission.id)

    def _start_scenario(self, progress: Progress, scenario: Scenario) -> Outcome:
        if missing := self._missing_warmups(progress, scenario):
            lines = [f"🔒 '{scenario.title}'은(는) 워밍업을 먼저 마쳐야 열려요.", "남은 워밍업:"]
            lines += [f"  • {self._title(m)} — /lab-start {m}" for m in missing]
            return self._scenario_out(
                "\n".join(lines),
                "start",
                "locked",
                4,
                id=scenario.id,
                extra={"missing_warmups": missing},
            )
        self.guard(scenario.env)
        if self.runner.restore(restore_mode(scenario.env)) != 0:
            return self._scenario_out(
                "실습 환경을 기본 상태로 되돌리지 못했어요. "
                "make -C agents/troubleshoot-lab up 을 다시 실행해 보세요.",
                "start",
                "failed",
                1,
                id=scenario.id,
            )
        attempt_no = prog.next_attempt_no(progress, scenario.id)
        self._record("scenario_started", scenario.id, attempt=attempt_no)
        attempt = prog.latest_attempt(self._progress(), scenario.id)
        lines = [
            f"🧪 {scenario.title}  (#{scenario.curriculum_no} · 시도 {attempt_no})",
            f"난이도 {DIFFICULTY_LABEL[scenario.difficulty]} · {FIELD_LABEL[scenario.field]} · "
            f"예상 {scenario.minutes}분",
            "",
            "증상",
            f"  {scenario.symptom.strip()}",
            "",
            f"흐름: {STEPS}",
            "",
            "👉 1단계: 장애를 넣기 전에 정상 상태를 측정하세요 → /lab-measure",
            "   (장애는 아직 주입되지 않았어요. 측정 후 /lab-inject 로 재현합니다.)",
        ]
        return self._scenario_out("\n".join(lines), "start", "ok", attempt=attempt)

    # --- measure (steps 1, 3, and after) --------------------------------------------

    def measure(self, skip_reason: str | None = None) -> Outcome:
        return self._guarded("measure", lambda: self._measure(skip_reason))

    def _measure_target(self) -> tuple[Attempt, str] | None:
        progress = self._progress()
        if (a := prog.active_attempt(progress)) is not None:
            return a, "baseline" if a.stage in ("started", "baseline_ok") else "fault"
        if self.session.get() is not None:
            return None
        finished = prog.finished_attempts(progress)
        if finished and finished[-1].end_type == "solved":
            return finished[-1], "after"
        return None

    def _measure(self, skip_reason: str | None) -> Outcome:
        target = self._measure_target()
        if target is None:
            return Outcome(
                "측정할 시나리오가 없어요. /lab-start <시나리오> 로 시작하세요.",
                "measure",
                "none",
                4,
            )
        attempt, phase = target
        scenario = self.catalog.scenarios[attempt.scenario_id]
        if skip_reason:
            metrics = skipped()
        else:
            try:
                metrics = self.measurer.run(scenario, attempt.attempt, phase)
            except MeasureError as exc:
                return self._scenario_out(
                    f"측정하지 못했어요: {exc}\n다시 시도하거나, 끝내 안 되면 "
                    '/lab-measure --skip "사유" 로 생략할 수 있어요(값은 비워 둬요).',
                    "measure",
                    "failed",
                    1,
                    attempt=attempt,
                )
        self._record(
            "measured",
            scenario.id,
            attempt=attempt.attempt,
            phase=phase,
            metrics=strip_display(metrics),
            skip_reason=skip_reason,
        )
        attempt = prog.latest_attempt(self._progress(), scenario.id)
        return self._scenario_out(
            self._measure_text(scenario, attempt, phase, metrics, skip_reason),
            "measure",
            "skipped" if skip_reason else "measured",
            attempt=attempt,
            extra={"phase": phase},
        )

    def _measure_text(self, scenario, attempt, phase, metrics, skip_reason) -> str:
        spec = scenario.measure
        base = attempt.measurements.get("baseline") if phase != "baseline" else None
        base_metrics = (
            {k: v.model_dump() for k, v in base.metrics.items()} if base is not None else None
        )
        head = (
            f"📏 측정 생략 ({PHASE_LABEL[phase]}, 사유: {skip_reason})"
            if skip_reason
            else f"📏 측정 완료 ({PHASE_LABEL[phase]}, {spec.duration_s}초, {spec.vus} VU, "
            f"{spec.method} {spec.path})"
        )
        lines = [head, format_table(metrics, base_metrics, skip_reason), ""]
        if phase == "baseline":
            lines.append("👉 2단계: 장애를 재현하세요 → /lab-inject")
        elif phase == "fault":
            lines += [
                "👉 3~4단계: 증상을 관찰하고 원인을 찾아보세요.",
                "   진단 명령: /lab-exec <서비스> <명령> (예: /lab-exec api ss -lntp)",
                "   막히면 /lab-hint",
                "👉 5단계: 고친 뒤 /lab-check",
            ]
        else:
            lines.append("👉 6단계: /lab-report 로 보고서를 작성하세요.")
        return "\n".join(lines)

    # --- inject (step 2) ------------------------------------------------------------

    def inject(self) -> Outcome:
        return self._guarded("inject", self._inject)

    def _inject(self) -> Outcome:
        attempt = self._active_attempt()
        if attempt is None:
            return Outcome(
                "진행 중인 시나리오가 없어요. /lab-start <시나리오> 로 시작하세요.",
                "inject",
                "none",
                4,
            )
        if attempt.stage == "started":
            return self._scenario_out(
                "장애를 넣기 전에 정상 상태를 먼저 측정해야 해요 → /lab-measure",
                "inject",
                "need_measure",
                4,
                attempt=attempt,
            )
        if attempt.stage != "baseline_ok":
            return self._scenario_out(
                "장애는 이미 재현되어 있어요. 장애 상태를 측정하고 원인을 찾아보세요.",
                "inject",
                "busy",
                4,
                attempt=attempt,
            )
        scenario = self.catalog.scenarios[attempt.scenario_id]
        self.guard(scenario.env)
        self.runner.mark_dirty(scenario.env)
        if self.runner.run(scenario.id, self._dir(scenario.id), "inject.sh") != 0:
            return self._scenario_out(
                "장애를 재현하지 못했어요. /lab-reset 후 다시 시도하세요.",
                "inject",
                "failed",
                1,
                attempt=attempt,
            )
        self._record("fault_injected", scenario.id, attempt=attempt.attempt)
        attempt = prog.latest_attempt(self._progress(), scenario.id)
        lines = ["💥 장애를 재현했어요.", "", "증상", f"  {scenario.symptom.strip()}"]
        if scenario.start_hint:
            lines += ["", f"확인해 보기: {scenario.start_hint.strip()}"]
        lines += ["", "👉 3단계: 같은 방법으로 장애 상태를 측정하세요 → /lab-measure"]
        return self._scenario_out("\n".join(lines), "inject", "ok", attempt=attempt)

    # --- diagnostics ----------------------------------------------------------------

    def exec(self, service: str, command: str, env_name: str | None = None) -> Outcome:
        def run() -> Outcome:
            env = env_name or self._active_env() or "compose"
            result = self.diagnoser.exec(service, command, env)
            return Outcome(result.output, "exec", result.outcome, result.exit_code, id=service)

        return self._guarded("exec", run)

    def shell(self, service: str, env_name: str | None = None) -> Outcome:
        env = env_name or self._active_env() or "compose"
        cmd = self.diagnoser.shell(service, env)
        return Outcome(f"내 터미널에서 실행하세요(대화형 쉘):\n  {cmd}", "shell", "ok", id=service)

    def _active_env(self) -> str | None:
        a = self._active_attempt()
        return self.catalog.scenarios[a.scenario_id].env if a else None

    # --- hint (step 4) --------------------------------------------------------------

    def hint(self) -> Outcome:
        progress = self._progress()
        active = self._active(progress)
        if active is None:
            return Outcome(
                "진행 중인 시나리오가 없어요. /lab-start <id> 로 시작하세요.", "hint", "none", 4
            )
        kind, item_id = active
        if kind == "mission":
            mission = self.catalog.missions[item_id]
            step = self.session.get().step_index
            return Outcome(
                "미션에는 힌트 대신 단계 안내가 있어요.\n\n" + _step_text(mission, step),
                "hint",
                "none",
                4,
                kind="mission",
                id=item_id,
            )
        attempt = prog.active_attempt(progress)
        if attempt.stage in ("started", "baseline_ok"):
            return self._scenario_out(
                "힌트는 장애를 재현한 뒤에 열 수 있어요.", "hint", "none", 4, attempt=attempt
            )
        if attempt.hints >= 3:
            return self._scenario_out(
                "힌트를 모두 열었어요 (3/3). 해설을 보려면 /lab-giveup 을 실행하세요.",
                "hint",
                "none",
                attempt=attempt,
            )
        level = attempt.hints + 1
        self._record("hint_opened", item_id, attempt=attempt.attempt, level=level)
        return self._scenario_out(
            f"💡 힌트 {level}/3\n{self.catalog.hints[item_id][level - 1]}",
            "hint",
            "ok",
            attempt=attempt,
            extra={"level": level},
        )

    # --- check (step 5) -------------------------------------------------------------

    def check(self, answer: str | None = None) -> Outcome:
        return self._guarded("check", lambda: self._check(answer))

    def _check(self, answer: str | None) -> Outcome:
        progress = self._progress()
        active = self._active(progress)
        if active is None:
            return Outcome("진행 중인 미션이나 시나리오가 없어요.", "check", "none", 4)
        kind, item_id = active
        if kind == "mission":
            return self._check_mission(progress, self.catalog.missions[item_id], answer)
        attempt = prog.active_attempt(progress)
        if attempt.stage != "fault_ok":
            need = (
                "정상 상태 측정과 장애 재현"
                if attempt.stage in ("started", "baseline_ok")
                else "장애 상태 측정"
            )
            return self._scenario_out(
                f"판정 전에 {need}을(를) 먼저 해 주세요 → /lab-measure"
                + (" , /lab-inject" if attempt.stage in ("started", "baseline_ok") else ""),
                "check",
                "need_measure",
                4,
                attempt=attempt,
            )
        scenario = self.catalog.scenarios[item_id]
        self.guard(scenario.env)
        if self.runner.run(item_id, self._dir(item_id), "verify.sh") != 0:
            return self._scenario_out(NOT_SOLVED, "check", "failed", 1, attempt=attempt)
        self._record("scenario_solved", item_id, attempt=attempt.attempt, hints_used=attempt.hints)
        after_text = self._after_measure(scenario, attempt)
        attempt = prog.latest_attempt(self._progress(), item_id)
        reaction_lines, reaction = self._react(item_id)
        text = "\n".join(
            [
                f"🎉 해결했어요! (힌트 {attempt.hints}개 사용)",
                "",
                after_text,
                "",
                self.catalog.solutions[item_id],
                "",
                "👉 6단계: /lab-report 로 장애 보고서를 쓰고 면접 질문에 답해 보세요.",
                "환경 원복: /lab-reset",
                *reaction_lines,
            ]
        )
        return self._scenario_out(
            text, "check", "solved", attempt=attempt, sync_suggested=True, extra=reaction
        )

    def _after_measure(self, scenario: Scenario, attempt: Attempt) -> str:
        try:
            metrics = self.measurer.run(scenario, attempt.attempt, "after")
        except MeasureError as exc:
            return f"해결 후 자동 측정에 실패했어요({exc}). /lab-measure 로 다시 측정할 수 있어요."
        self._record(
            "measured",
            scenario.id,
            attempt=attempt.attempt,
            phase="after",
            metrics=strip_display(metrics),
        )
        latest = prog.latest_attempt(self._progress(), scenario.id)
        return self._measure_text(scenario, latest, "after", metrics, None).rsplit("\n\n", 1)[0]

    def _check_mission(self, progress: Progress, mission: Mission, answer: str | None) -> Outcome:
        index = self.session.get().step_index
        step = mission.steps[index]
        if step.check == "answer" and not answer:
            return Outcome(
                f"이 단계는 값을 입력해야 해요: /lab-check <값>\n{step.prompt}",
                "check",
                "failed",
                1,
                kind="mission",
                id=mission.id,
            )
        self.guard(mission.env)
        args = [step.id] + ([answer] if step.check == "answer" and answer else [])
        if self.runner.run(mission.id, self._dir(mission.id), "verify.sh", *args) != 0:
            return Outcome(
                "아직 통과하지 못했어요. 안내를 다시 확인해 보세요.\n\n"
                + _step_text(mission, index),
                "check",
                "failed",
                1,
                kind="mission",
                id=mission.id,
            )
        if index + 1 < len(mission.steps):
            self.session.set(mission.id, index + 1)
            return Outcome(
                "✅ 통과!\n\n" + _step_text(mission, index + 1),
                "check",
                "mission_step_passed",
                kind="mission",
                id=mission.id,
            )
        if not prog.mission_done(progress, mission.id):
            self._record("mission_completed", mission.id)
        self.session.clear()
        self.runner.restore(restore_mode(mission.env))
        unlocked = self._newly_unlocked(mission.id)
        lines = [f"🏁 '{mission.title}' 완료!"]
        if unlocked:
            lines += ["", "이제 시작할 수 있어요:"]
            lines += [f"  • {s.title} — /lab-start {s.id}" for s in unlocked]
        reaction_lines, reaction = self._react(mission.id)
        return Outcome(
            "\n".join([*lines, *reaction_lines]),
            "check",
            "mission_completed",
            kind="mission",
            id=mission.id,
            extra=reaction,
        )

    def _newly_unlocked(self, mission_id: str) -> list[Scenario]:
        progress = self._progress()
        return [
            s
            for s in self.catalog.scenarios.values()
            if mission_id in s.warmups
            and not self._missing_warmups(progress, s)
            and prog.scenario_status(progress, s.id) not in ("solved", "gave_up")
        ]

    # --- giveup ---------------------------------------------------------------------

    def giveup(self) -> Outcome:
        attempt = self._active_attempt()
        if attempt is None:
            text = "포기할 시나리오가 없어요."
            if self.session.get():
                text += " 미션은 /lab-reset 으로 그만둘 수 있어요."
            return Outcome(text, "giveup", "none", 4)
        sid = attempt.scenario_id
        self._record("scenario_gave_up", sid, attempt=attempt.attempt, hints_used=attempt.hints)
        attempt = prog.latest_attempt(self._progress(), sid)
        text = "\n".join(
            [
                "🏳️ 포기로 기록했어요. 해설은 다음과 같아요.",
                "",
                self.catalog.solutions[sid],
                "",
                "👉 6단계: 포기해도 회고는 해요 → /lab-report",
                "환경 원복: /lab-reset",
            ]
        )
        return self._scenario_out(text, "giveup", "gave_up", attempt=attempt, sync_suggested=True)

    # --- report (step 6) ------------------------------------------------------------

    def report(self, done: bool = False, item_id: str | None = None) -> Outcome:
        finished = [
            a
            for a in prog.finished_attempts(self._progress())
            if item_id is None or a.scenario_id == item_id
        ]
        if not finished:
            return Outcome(
                "보고서를 쓸 시도가 없어요. 시나리오를 해결하거나 포기한 뒤에 쓸 수 있어요.",
                "report",
                "none",
                4,
                id=item_id,
            )
        attempt = finished[-1]
        scenario = self.catalog.scenarios[attempt.scenario_id]
        rel = rep.report_rel_path(attempt)
        if not done:
            rel, created = rep.create_draft(attempt, scenario, self.repo_root)
            if created:
                text = (
                    f"📝 보고서 초안을 만들었어요: {rel}\n"
                    "측정표와 면접 질문은 채워져 있어요. 증상·원인·분석 과정·해결 방법·재발 방지와 "
                    "면접 질문 답을 직접 쓴 뒤 /lab-report --done 을 실행하세요."
                )
                return self._scenario_out(
                    text, "report", "created", attempt=attempt, extra={"report": str(rel)}
                )
            return self._scenario_out(
                f"보고서가 이미 있어요: {rel}\n다 쓰면 /lab-report --done",
                "report",
                "exists",
                attempt=attempt,
                extra={"report": str(rel)},
            )
        path = self.repo_root / rel
        if not path.exists():
            return self._scenario_out(
                f"보고서 파일이 없어요: {rel}\n먼저 /lab-report 로 초안을 만드세요.",
                "report",
                "none",
                4,
                attempt=attempt,
            )
        missing, answered = rep.check_done(path, scenario)
        if missing:
            return self._scenario_out(
                "아직 비어 있는 항목이 있어요:\n" + "\n".join(f"  - {m}" for m in missing),
                "report",
                "incomplete",
                1,
                attempt=attempt,
                extra={"missing": missing},
            )
        if not attempt.reviewed:
            self._record(
                "report_completed",
                scenario.id,
                attempt=attempt.attempt,
                report=str(rel),
                answered=answered,
            )
        attempt = prog.latest_attempt(self._progress(), scenario.id)
        return self._scenario_out(
            f"✅ 회고 완료로 기록했어요 ({rel}, 면접 질문 {answered}개 답변).",
            "report",
            "reviewed",
            attempt=attempt,
            sync_suggested=True,
        )

    # --- reset ----------------------------------------------------------------------

    def reset(self, item_id: str | None = None) -> Outcome:
        return self._guarded("reset", lambda: self._reset(item_id))

    def _reset(self, item_id: str | None) -> Outcome:
        progress = self._progress()
        active = self._active(progress)
        if item_id is None and active is not None:
            item_id = active[1]
        if item_id is None:
            for env_name in ("compose", "kind"):
                self.guard(env_name)
            return _reset_outcome(self.runner.restore("all"), None, None)
        kind = self.catalog.kind(item_id)
        if kind is None:
            return Outcome(f"'{item_id}'을(를) 찾을 수 없어요.", "reset", "unknown", 2, id=item_id)
        item = self.catalog.get(item_id)
        self.guard(item.env)
        if kind == "mission":
            if active == ("mission", item_id):
                self.session.clear()
            return _reset_outcome(self.runner.restore(restore_mode(item.env)), kind, item_id)
        code = self.runner.run(item_id, self._dir(item_id), "reset.sh")
        attempt = prog.active_attempt(progress)
        if code == 0 and attempt is not None and attempt.scenario_id == item_id:
            self._record("scenario_reset", item_id, attempt=attempt.attempt, was_active=True)
        return _reset_outcome(code, kind, item_id)


def _reset_outcome(code: int, kind: str | None, item_id: str | None) -> Outcome:
    if code != 0:
        return Outcome(
            "원복에 실패했어요. make -C agents/troubleshoot-lab up 으로 환경을 다시 준비해 보세요.",
            "reset",
            "failed",
            1,
            kind=kind,
            id=item_id,
        )
    return Outcome(
        "🧹 깨끗한 상태로 되돌렸어요. (측정 기록과 보고서는 그대로 남아 있어요)",
        "reset",
        "ok",
        kind=kind,
        id=item_id,
    )


def _step_text(mission: Mission, index: int) -> str:
    step: MissionStep = mission.steps[index]
    lines = [f"단계 {index + 1}/{len(mission.steps)}", step.guide.strip(), "", "따라 해 보기:"]
    lines += [f"  {line}" for line in step.command.strip().splitlines()]
    if step.check == "answer":
        lines += ["", f"확인: {step.prompt.strip()}", "값을 찾았으면 /lab-check <값>"]
    else:
        lines += ["", "다 했으면 /lab-check"]
    return "\n".join(lines)


def default_guard(lab_root: Path) -> Guard:
    return lambda env_name: check_for(env_name, lab_root)
