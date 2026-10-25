"""``lab`` CLI (contracts/cli.md). Learning commands print Korean text plus a final
``LAB_RESULT {json}`` line for the slash commands; ``daily`` prints a summary JSON line.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import IO

import httpx

from shared.config import MissingEnvError, require_env
from shared.logging import configure
from troubleshoot_lab import daily
from troubleshoot_lab.catalog import load_catalog
from troubleshoot_lab.diag import Diagnoser
from troubleshoot_lab.guard import kubeconfig_path
from troubleshoot_lab.learn import Learner, Outcome, default_guard
from troubleshoot_lab.measure import Measurer
from troubleshoot_lab.progress import ProgressStore
from troubleshoot_lab.runner import ScriptRunner
from troubleshoot_lab.session import Session
from troubleshoot_lab.sync import sync
from troubleshoot_lab.weekly import KST

LAB_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = LAB_ROOT.parents[1]
DAILY_RUN_TIME = time(8, 40)  # matches the cron (research R8)

LEARN_COMMANDS = (
    "list",
    "start",
    "measure",
    "inject",
    "exec",
    "shell",
    "hint",
    "check",
    "giveup",
    "report",
    "reset",
)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lab", description="troubleshoot-lab practice CLI")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="미션·시나리오 목록과 진행 상황")
    start = sub.add_parser("start", help="미션 또는 시나리오 시작")
    start.add_argument("id")
    measure = sub.add_parser("measure", help="정상·장애·해결 후 지표 측정 (k6 + 자원)")
    measure.add_argument("--skip", metavar="사유", help="측정을 생략하고 사유만 기록")
    sub.add_parser("inject", help="정상 측정 뒤 장애 재현")
    ex = sub.add_parser("exec", help="대상 서비스 공간의 진단 컨테이너에서 명령 실행")
    ex.add_argument("--env", choices=["compose", "kind"])
    ex.add_argument("service")
    ex.add_argument("cmd", nargs=argparse.REMAINDER)
    sh = sub.add_parser("shell", help="대화형 진단 쉘 명령 출력")
    sh.add_argument("--env", choices=["compose", "kind"])
    sh.add_argument("service")
    sub.add_parser("hint", help="진행 중 시나리오의 다음 힌트")
    check = sub.add_parser("check", help="진행 중 항목 검증")
    check.add_argument("answer", nargs="?")
    sub.add_parser("giveup", help="포기하고 해설 보기")
    report = sub.add_parser("report", help="장애 보고서 초안 만들기 / 완료 확인")
    report.add_argument("--done", action="store_true")
    report.add_argument("id", nargs="?")
    reset = sub.add_parser("reset", help="원복")
    reset.add_argument("id", nargs="?")
    sub.add_parser("sync", help="진행 기록만 커밋·push (main 브랜치)")
    sub.add_parser("validate", help="카탈로그 검사")
    sub.add_parser("env", help="사용자 쉘용 export 문 출력")
    d = sub.add_parser("daily", help="오늘의 문제·주간 요약 게시")
    d.add_argument("--target", choices=["test", "lab"])
    d.add_argument("--dry-run", action="store_true")
    d.add_argument("--force", action="store_true")
    d.add_argument("--post", choices=["daily", "weekly", "both"], default="daily")
    d.add_argument("--today", type=date.fromisoformat, metavar="YYYY-MM-DD")
    return p


def _command(parts: list[str]) -> str:
    if parts and parts[0] == "--":
        parts = parts[1:]
    # tokens are re-joined with spaces so pipes typed through the slash command still work
    return " ".join(parts) if parts else "true"


def _emit(outcome: Outcome, out: IO[str]) -> int:
    out.write(outcome.text.rstrip() + "\n")
    out.write("LAB_RESULT " + json.dumps(outcome.result(), ensure_ascii=False) + "\n")
    return outcome.exit_code


def make_learner(lab_root: Path, environ: Mapping[str, str]) -> Learner:
    guard = default_guard(lab_root)
    return Learner(
        load_catalog(lab_root),
        ProgressStore(lab_root / "data" / "progress.json"),
        Session(lab_root / ".lab-state"),
        ScriptRunner(lab_root, environ=environ),
        guard=guard,
        measurer=Measurer(lab_root, guard=guard),
        diagnoser=Diagnoser(lab_root, guard=guard),
        repo_root=lab_root.parents[1],
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    lab_root: Path = LAB_ROOT,
    repo_root: Path = REPO_ROOT,
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
    out: IO[str] | None = None,
    learner_factory: Callable[[Path, Mapping[str, str]], Learner] = make_learner,
    http_factory: Callable[[], httpx.Client] = httpx.Client,
    sync_fn: Callable[..., object] = sync,
    base_delay: float = 1.0,
) -> int:
    environ = os.environ if environ is None else environ
    out = out or sys.stdout
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0) and 2
    configure()

    if args.command in LEARN_COMMANDS:
        learner = learner_factory(lab_root, environ)
        outcome = {
            "list": lambda: learner.list(),
            "start": lambda: learner.start(args.id),
            "measure": lambda: learner.measure(args.skip),
            "inject": lambda: learner.inject(),
            "exec": lambda: learner.exec(args.service, _command(args.cmd), args.env),
            "shell": lambda: learner.shell(args.service, args.env),
            "report": lambda: learner.report(args.done, args.id),
            "hint": lambda: learner.hint(),
            "check": lambda: learner.check(args.answer),
            "giveup": lambda: learner.giveup(),
            "reset": lambda: learner.reset(args.id),
        }[args.command]()
        return _emit(outcome, out)

    if args.command == "sync":
        result = sync_fn(repo_root)
        _emit(Outcome(result.text, "sync", result.outcome, result.exit_code), out)
        return result.exit_code

    if args.command == "validate":
        catalog = load_catalog(lab_root)
        out.write(
            f"미션 {len(catalog.missions)}개, 시나리오 {len(catalog.scenarios)}개, "
            f"오류 {len(catalog.errors)}\n"
        )
        if catalog.plan is not None:
            done: set[str] = set()
            out.write("학습 계획 21일:\n")
            for day in catalog.plan.days:
                ids = day.items or day.pool or []
                minutes = [
                    catalog.minutes_with_warmups(i, done) for i in (ids if day.pool else ids[:1])
                ]
                span = (
                    f"{min(minutes)}~{max(minutes)}" if len(set(minutes)) > 1 else str(minutes[0])
                )
                out.write(f"  {day.day:2d}일 차 ({span}분) {day.topic}\n")
        for err in catalog.errors:
            out.write(f"  - {err}\n")
        return 2 if catalog.errors else 0

    if args.command == "env":
        work = lab_root / ".lab-state" / "work"
        compose = f"{lab_root / 'environment' / 'compose.yaml'}:{work / 'compose.override.yaml'}"
        out.write(
            f"export KUBECONFIG={kubeconfig_path(lab_root)}\n"
            f"export COMPOSE_FILE={compose}\n"
            "export COMPOSE_PROJECT_NAME=troubleshoot-lab\n"
            f"export LAB_WORK={work}\n"
        )
        return 0

    return _daily(
        args,
        lab_root=lab_root,
        environ=environ,
        now=now,
        out=out,
        http_factory=http_factory,
        base_delay=base_delay,
    )


def _daily(args, *, lab_root, environ, now, out, http_factory, base_delay) -> int:
    target = args.target or environ.get("LAB_SLACK_TARGET") or "test"
    if target not in ("test", "lab"):
        print(f"error: LAB_SLACK_TARGET must be test or lab, got {target}", file=sys.stderr)
        return 2
    safe = args.dry_run or target == "test"
    if (args.force or args.today) and not safe:
        print("error: --force/--today need --dry-run or --target test", file=sys.stderr)
        return 2
    names = (
        []
        if args.dry_run
        else [daily.TEST_WEBHOOK] + ([daily.LAB_WEBHOOK] if target == "lab" else [])
    )
    try:
        env = {**environ, **require_env(*names, environ=environ)}
    except MissingEnvError as exc:
        print(f"error: missing environment variables: {', '.join(exc.names)}", file=sys.stderr)
        return 2
    if args.today:
        now = datetime.combine(args.today, DAILY_RUN_TIME, KST).astimezone(UTC)
    now = now or datetime.now(UTC)
    with http_factory() as http:
        result = daily.run(
            daily.RunContext(
                lab_root=lab_root,
                env=env,
                http=http,
                now=now,
                target=target,
                dry_run=args.dry_run,
                force=args.force,
                post=args.post,
                out=out,
                base_delay=base_delay,
            )
        )
    out.write(daily.summary_json(result) + "\n")
    return daily.exit_code(result)
