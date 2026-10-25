"""Commit and push only data/progress.json and docs/reports/, after the learner agrees (R7, R25)."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from shared.logging import get_logger
from shared.retry import retryable

log = get_logger(__name__)

PROGRESS_REL = "agents/troubleshoot-lab/data/progress.json"
REPORTS_REL = "agents/troubleshoot-lab/docs/reports"
PATHS = [PROGRESS_REL, REPORTS_REL]
BRANCH = "main"


class GitError(Exception):
    pass


Git = Callable[[list[str]], subprocess.CompletedProcess]


def _git(repo_root: Path) -> Git:
    def run(args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=repo_root, capture_output=True, text=True, timeout=60, check=False
        )

    return run


@dataclass
class SyncResult:
    exit_code: int
    text: str
    outcome: str


def sync(
    repo_root: Path,
    *,
    git: Git | None = None,
    now: datetime | None = None,
    base_delay: float = 1.0,
) -> SyncResult:
    git = git or _git(repo_root)

    def ok(args: list[str]) -> str:
        res = git(args)
        if res.returncode != 0:
            raise GitError(f"git {args[0]} failed: {(res.stderr or res.stdout).strip()[:200]}")
        return res.stdout.strip()

    branch = ok(["rev-parse", "--abbrev-ref", "HEAD"])
    if branch != BRANCH:
        return SyncResult(
            4,
            f"지금 브랜치가 {branch} 라서 push하지 않았어요. 매일 알림은 {BRANCH}의 기록을 읽으니 "
            f"{BRANCH}에서 다시 /lab-check 하거나 bin/lab sync 를 실행하세요. "
            "기록은 로컬에 남아 있어요.",
            "wrong_branch",
        )

    changed = bool(ok(["status", "--porcelain", "--", *PATHS]))
    if changed:
        stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M UTC")
        ok(["add", "--", *PATHS])  # new report files are untracked
        ok(["commit", "-m", f"lab: progress update ({stamp}) [skip ci]", "--", *PATHS])

    ahead = ok(["rev-list", "--count", f"origin/{BRANCH}..HEAD"])
    if not changed and ahead == "0":
        return SyncResult(0, "올릴 진행 기록 변경이 없어요.", "unchanged")

    @retryable(retry_on=(GitError,), max_attempts=3, base_delay=base_delay, target="git:push")
    def push() -> None:
        ok(["pull", "--rebase", "--autostash", "origin", BRANCH])
        ok(["push", "origin", f"HEAD:{BRANCH}"])

    try:
        push()
    except GitError as exc:
        log.warning("progress_push_failed", extra={"fields": {"error": str(exc)}})
        return SyncResult(
            1,
            "push에 실패했어요(네트워크 등). 커밋은 로컬에 남아 있고, 다음 sync 때 다시 올라가요.",
            "failed",
        )
    return SyncResult(0, "✅ 진행 기록을 커밋하고 push했어요.", "pushed")
