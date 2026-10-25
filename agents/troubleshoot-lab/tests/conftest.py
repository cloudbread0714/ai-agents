from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from tl_support import NOW, FakeMeasurer, FakeRunner, make_catalog, scenario_spec
from troubleshoot_lab.catalog import load_catalog
from troubleshoot_lab.learn import Learner
from troubleshoot_lab.progress import ProgressStore
from troubleshoot_lab.session import Session

REAL_LAB = Path(__file__).resolve().parents[1]


def pytest_collection_modifyitems(config, items):
    if os.environ.get("LAB_SANDBOX") == "1":
        return
    skip = pytest.mark.skip(reason="needs real docker + kind; set LAB_SANDBOX=1")
    for item in items:
        if "sandbox" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    return tmp_path / "repo"


@pytest.fixture
def lab_root(repo_root: Path) -> Path:
    """Warmups m-one, m-two, concept c-one, three scenarios and a valid 21-day plan,
    laid out like the real repo (repo/agents/troubleshoot-lab) with the report template."""
    root = repo_root / "agents" / "troubleshoot-lab"
    root.mkdir(parents=True)
    (root / "templates").mkdir()
    shutil.copy(REAL_LAB / "templates" / "report.md", root / "templates" / "report.md")
    return make_catalog(
        root,
        scenarios=[
            scenario_spec("d-easy", warmups=["m-one", "m-two"], minutes=30, no="3"),
            scenario_spec("w-easy", warmups=["m-one"], fields=["network"], no="2"),
            scenario_spec("d-mid", difficulty="intermediate", no="7"),
        ],
    )


@pytest.fixture
def runner() -> FakeRunner:
    return FakeRunner()


@pytest.fixture
def measurer() -> FakeMeasurer:
    return FakeMeasurer()


@pytest.fixture
def guard_calls() -> list[str]:
    return []


@pytest.fixture
def learner(lab_root, repo_root, runner, measurer, guard_calls):
    clock = iter(NOW.replace(minute=m) for m in range(0, 60))
    return Learner(
        load_catalog(lab_root),
        ProgressStore(lab_root / "data" / "progress.json"),
        Session(lab_root / ".lab-state"),
        runner,
        guard=guard_calls.append,
        measurer=measurer,
        repo_root=repo_root,
        now=lambda: next(clock),
    )


@pytest.fixture
def store(lab_root) -> ProgressStore:
    return ProgressStore(lab_root / "data" / "progress.json")
