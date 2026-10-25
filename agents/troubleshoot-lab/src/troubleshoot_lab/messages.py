"""Slack Block Kit payloads (contracts/slack-message.md).

The daily message uses only public fields (title, difficulty, field, curriculum number,
symptom, plan topic/practice, warmup titles). Hints, solutions, tags, ``start_hint``,
interview questions and measurement specs never reach Slack (FR-031, SC-002).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from shared.slack import escape_mrkdwn
from troubleshoot_lab import progress as prog
from troubleshoot_lab.catalog import Catalog
from troubleshoot_lab.models import DIFFICULTY_LABEL, FIELD_LABEL, Progress
from troubleshoot_lab.planner import DayPick
from troubleshoot_lab.weekly import KST, WeeklySummary

WEEKDAYS = "월화수목금토일"
CLI = "agents/troubleshoot-lab/bin/lab"
STEPS = "정상 상태 측정 → 장애 재현 → 관찰 → 분석 → 해결 → 보고서"


def _header(text: str, test_mode: bool) -> tuple[str, dict[str, Any]]:
    title = f"{'[TEST] ' if test_mode else ''}{text}"
    return title, {"type": "header", "text": {"type": "plain_text", "text": title, "emoji": True}}


def _section(text: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _context(text: str) -> dict[str, Any]:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}


def _heading(pick: DayPick, catalog: Catalog) -> str:
    if pick.kind == "day" and pick.plan_day is not None:
        suffix = " (종합: 후보 중 1개)" if pick.composite else ""
        return f"📚 {pick.day}일 차 · {pick.plan_day.week}주 차: {pick.plan_day.topic}{suffix}"
    if pick.kind == "catchup":
        return "🔁 따라잡기 날"
    if pick.kind == "extra":
        total = len(catalog.plan.extras) if catalog.plan else 0
        return f"🧩 심화 문제 {pick.extra_index}/{total}"
    return "🔁 복습 문제"


def build_daily(
    pick: DayPick, catalog: Catalog, progress: Progress, date_kst: date, *, test_mode: bool = False
) -> dict[str, Any]:
    title, header = _header(_heading(pick, catalog), test_mode)
    blocks: list[dict[str, Any]] = [header]
    time_line = f"⏱ 예상 {pick.minutes}분 (60~90분 기준)"
    if pick.minutes > 90:
        time_line += "   ⚠️ 오늘 분량이 90분을 넘어요"
    elif pick.minutes < 60:
        time_line += "   남는 시간에는 '시간이 남으면'이나 밀린 문제를 해 보세요"
    intro = [time_line]
    if pick.kind == "day" and pick.plan_day is not None:
        intro.append(f"*오늘 실습* {escape_mrkdwn(pick.plan_day.practice)}")
    blocks.append(_section("\n".join(intro)))

    done = prog.done_missions(progress)
    if pick.main_kind == "mission":
        m = catalog.missions[pick.main_id]
        blocks.append(_section(f"*🧭 개념 미션* {escape_mrkdwn(m.title)} — `/lab-start {m.id}`"))
    else:
        s = catalog.scenarios[pick.main_id]
        lines = [
            f"*🧪 주 문제* {escape_mrkdwn(s.title)}" + ("  · 복습" if pick.review_flag else "")
        ]
        if pick.review_flag and pick.plan_day is not None:
            lines.append(f"이번에는 이 관점으로: {escape_mrkdwn(pick.plan_day.practice)}")
        lines += [
            f"*난이도* {DIFFICULTY_LABEL[s.difficulty]}   *분야* {FIELD_LABEL[s.field]}   "
            f"*#*{s.curriculum_no}",
            f"*증상*\n{escape_mrkdwn(s.symptom.strip())}",
            f"*시작* `/lab-start {s.id}`  → {STEPS}",
        ]
        blocks.append(_section("\n".join(lines)))
        warmups = []
        for mid in s.warmups:
            mission = catalog.missions.get(mid)
            name = escape_mrkdwn(mission.title if mission else mid)
            warmups.append(
                f"• ✅ {name} — 완료됨" if mid in done else f"• ⬜ {name} — `/lab-start {mid}`"
            )
        if all(mid in done for mid in s.warmups):
            warmups.append("워밍업을 모두 마쳤어요. 바로 시작하세요.")
        blocks.append(_section("*워밍업*\n" + "\n".join(warmups)))

    tail = []
    if pick.second_id:
        second = catalog.get(pick.second_id)
        tail.append(
            f"*시간이 남으면* {escape_mrkdwn(second.title if second else pick.second_id)} — "
            f"`/lab-start {pick.second_id}`"
        )
    if pick.backlog:
        tail.append("*밀린 문제*")
        tail += [
            f"• {escape_mrkdwn(catalog.scenarios[b].title)} — `/lab-start {b}`"
            for b in pick.backlog
        ]
    active = prog.active_scenario(progress)
    if active and active != pick.main_id:
        other = catalog.scenarios.get(active)
        name = escape_mrkdwn(other.title if other else active)
        tail.append(f"⚠️ 진행 중인 시나리오({name})가 있어요. 끝내거나 `/lab-reset` 후 시작하세요.")
    if tail:
        blocks.append(_section("\n".join(tail)))
    blocks.append(
        _context(
            f"{date_kst.isoformat()} ({WEEKDAYS[date_kst.weekday()]}) · "
            f"터미널: `{CLI} start {pick.main_id}`"
        )
    )
    return {"text": title, "blocks": blocks}


def build_weekly(summary: WeeklySummary, *, test_mode: bool = False) -> dict[str, Any]:
    period_end = summary.until.astimezone(KST).date()
    title, header = _header(
        f"📊 이번 주 학습 요약 ({summary.week_start:%m/%d}~{period_end:%m/%d})", test_mode
    )
    blocks: list[dict[str, Any]] = [header]
    lines = [f"*진행* {summary.progress_label}"]
    if summary.empty:
        lines.append("이번 주에는 기록이 없어요. 다음 주제부터 시작해 볼까요?")
    else:
        lines += [
            f"*해결* {summary.solved}개   *포기* {summary.gave_up}개   *힌트* {summary.hints}회",
            f"*회고* 완료 {summary.reviewed}개 · 면접 질문 답변 {summary.answered}개",
        ]
        weak = FIELD_LABEL[summary.weak_field] if summary.weak_field else "기록 없음"
        lines.append(f"*약한 분야* {weak}")
    if summary.pending:
        lines.append("*회고 대기*")
        lines += [f"• {escape_mrkdwn(t)} (시도 {n})" for t, n in summary.pending]
    lines.append(f"*밀린 문제* {summary.backlog}개")
    if summary.next_topic:
        lines.append(f"*다음 주제* {escape_mrkdwn(summary.next_topic)}")
    blocks.append(_section("\n".join(lines)))
    return {"text": title, "blocks": blocks}
