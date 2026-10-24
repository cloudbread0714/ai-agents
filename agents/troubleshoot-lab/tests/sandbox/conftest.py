"""Fixtures for tests against the real practice environment (LAB_SANDBOX=1, research R13)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from troubleshoot_lab.catalog import load_catalog
from troubleshoot_lab.runner import ScriptRunner

LAB_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = LAB_ROOT.parents[1]
ENV_DIR = LAB_ROOT / "environment"


class Sandbox:
    def __init__(self):
        self.runner = ScriptRunner(LAB_ROOT)
        self.catalog = load_catalog(LAB_ROOT)

    def env(self) -> dict[str, str]:
        env = self.runner.env("sandbox-test", ENV_DIR)
        work = LAB_ROOT / ".lab-state" / "work"
        env["COMPOSE_FILE"] = f"{ENV_DIR / 'compose.yaml'}:{work / 'compose.override.yaml'}"
        return env

    def capture(self, script: str, *args: str) -> str:
        res = subprocess.run(
            [str(ENV_DIR / script), *args],
            cwd=ENV_DIR,
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=600,
            check=True,
        )
        return res.stdout.strip()

    def fingerprint(self, mode: str) -> str:
        return self.capture("fingerprint.sh", mode)

    def healthcheck(self, mode: str) -> int:
        return self.runner.run("environment", ENV_DIR, "healthcheck.sh", mode)

    def shell(self, command: str) -> subprocess.CompletedProcess:
        """Run a mission step command verbatim from the repo root, like the learner would."""
        return subprocess.run(
            ["bash", "-c", command],
            cwd=REPO_ROOT,
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )

    def answers(self, mission_id: str) -> dict[str, str]:
        path = LAB_ROOT / ".lab-state" / "missions" / mission_id / "answers.json"
        return json.loads(path.read_text()) if path.exists() else {}


@pytest.fixture(scope="session")
def sandbox() -> Sandbox:
    if os.environ.get("LAB_SANDBOX_SKIP_UP") != "1":
        subprocess.run(["make", "-C", str(LAB_ROOT), "up"], check=True, timeout=1800)
    return Sandbox()
