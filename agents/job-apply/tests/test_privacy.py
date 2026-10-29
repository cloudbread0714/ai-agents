"""FR-024 on the real repository: personal paths are git-ignored."""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
PATHS = [
    "agents/job-apply/private/x",
    "agents/job-apply/applications/x",
    "agents/job-apply/.job-state/x",
    "agents/job-apply/.env",
]


@pytest.mark.skipif(
    shutil.which("git") is None or not (REPO / ".git").exists(), reason="needs the git repo"
)
def test_personal_paths_are_ignored():
    proc = subprocess.run(["git", "check-ignore", *PATHS], cwd=REPO, capture_output=True, text=True)
    assert proc.stdout.split() == PATHS
