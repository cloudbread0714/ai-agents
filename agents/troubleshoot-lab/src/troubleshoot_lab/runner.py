"""Run mission/scenario/environment scripts with the contract environment (contracts/content.md).

Script output goes to ``.lab-state/logs/`` only: verify failures must not reveal what is
still wrong (FR-012), so callers get an exit code, never the output.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from shared.logging import get_logger
from troubleshoot_lab.guard import EnvNotReady, SandboxError, kubeconfig_path

log = get_logger(__name__)

TIMEOUTS = {"setup.sh": 300, "inject.sh": 300, "reset.sh": 300, "restore.sh": 600, "verify.sh": 60}
TIMEOUT_EXIT = 124


class Runner(Protocol):
    def run(self, item_id: str, item_dir: Path, script: str, *args: str) -> int: ...
    def restore(self, mode: str) -> int: ...
    def mark_dirty(self, env_name: str) -> None: ...


class ScriptRunner:
    def __init__(self, lab_root: Path, *, environ: Mapping[str, str] | None = None):
        self.lab_root = lab_root
        self.state = lab_root / ".lab-state"
        self.environ = dict(os.environ if environ is None else environ)

    def env(self, item_id: str, item_dir: Path) -> dict[str, str]:
        return {
            **self.environ,
            "LAB_ROOT": str(self.lab_root),
            "LAB_STATE": str(self.state),
            "LAB_WORK": str(self.state / "work"),
            "LAB_ITEM_DIR": str(item_dir),
            "LAB_ITEM_ID": item_id,
            "KUBECONFIG": str(kubeconfig_path(self.lab_root)),
            "COMPOSE_PROJECT_NAME": "troubleshoot-lab",
        }

    def run(self, item_id: str, item_dir: Path, script: str, *args: str) -> int:
        logs = self.state / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        log_path = logs / f"{item_id}-{script.removesuffix('.sh')}-{stamp}.log"
        with log_path.open("w", encoding="utf-8") as out:
            try:
                code = subprocess.run(
                    [str(item_dir / script), *args],
                    cwd=item_dir,
                    env=self.env(item_id, item_dir),
                    stdout=out,
                    stderr=subprocess.STDOUT,
                    timeout=TIMEOUTS.get(script, 300),
                    check=False,
                ).returncode
            except subprocess.TimeoutExpired:
                out.write(f"\nlab: {script} timed out\n")
                code = TIMEOUT_EXIT
        log.info(
            "script_finished",
            extra={
                "fields": {"item": item_id, "script": script, "exit": code, "log": str(log_path)}
            },
        )
        if code in (3, 5):
            message = _last_lab_message(log_path) or "실습 환경을 확인할 수 없어요"
            raise (SandboxError if code == 3 else EnvNotReady)(message)
        return code

    def restore(self, mode: str) -> int:
        return self.run("environment", self.lab_root / "environment", "restore.sh", mode)

    def mark_dirty(self, env_name: str) -> None:
        self.state.mkdir(parents=True, exist_ok=True)
        side = "kind" if env_name == "kind" else "compose"
        (self.state / f"dirty-{side}").touch()


def _last_lab_message(log_path: Path) -> str | None:
    lines = [
        ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.startswith("lab: ")
    ]
    return lines[-1].removeprefix("lab: ") if lines else None
