"""Static checks on the real catalog (research R13 정적). No Docker or network needed."""

import os
import re
import subprocess
from pathlib import Path

import pytest

from troubleshoot_lab.catalog import load_catalog
from troubleshoot_lab.models import CATEGORIES, DIFFICULTY_RANK

LAB_ROOT = Path(__file__).resolve().parents[2]
CONTENT_DIRS = ("missions", "scenarios", "templates")
SCRIPT_DIRS = (*CONTENT_DIRS, "lib", "environment")
REQUIRED_HEAD = ["#!/usr/bin/env bash", "set -euo pipefail", 'source "$LAB_ROOT/lib/common.sh"']
# kubectl / docker / docker compose must go through k / dk / dc (lib/common.sh) so the guard runs.
BARE_TOOL = re.compile(r"(^|[\s;|&(`])(kubectl|docker)(\s|$)")
INTERACTIVE = re.compile(r"(\s-it\b|\s-ti\b|\bvi\b|\bvim\b|\bnano\b|\bless\b|\bmore\b)")

FR004_TOPICS = {
    "docker": ["docker-build", "docker-run-basics", "docker-logs", "docker-exec", "compose-basics"],
    "kubernetes": [
        "k8s-get-pods",
        "k8s-describe",
        "k8s-logs",
        "k8s-exec",
        "k8s-service-basics",
        "k8s-rollout",
    ],
    "web": ["curl-basics", "http-headers", "cache-headers"],
}


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(LAB_ROOT)


def _scripts(*dirs):
    return sorted(p for d in dirs for p in (LAB_ROOT / d).rglob("*.sh"))


def test_catalog_loads_without_errors(catalog):
    assert catalog.errors == []
    assert len(catalog.scenarios) >= 9


def test_every_category_and_difficulty_is_covered(catalog):
    pairs = {(s.category, s.difficulty) for s in catalog.scenarios.values()}
    assert pairs >= {(c, d) for c in CATEGORIES for d in DIFFICULTY_RANK}


def test_fr004_topics_have_missions(catalog):
    for category, ids in FR004_TOPICS.items():
        for mission_id in ids:
            assert catalog.missions[mission_id].category == category


@pytest.mark.parametrize(
    "script", _scripts(*SCRIPT_DIRS), ids=lambda p: str(p.relative_to(LAB_ROOT))
)
def test_script_syntax_and_permissions(script):
    if script.name != "common.sh":  # sourced, not executed
        assert os.access(script, os.X_OK), "not executable"
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "script", _scripts(*CONTENT_DIRS), ids=lambda p: str(p.relative_to(LAB_ROOT))
)
def test_content_scripts_start_with_guard(script):
    lines = script.read_text().splitlines()
    assert lines[:3] == REQUIRED_HEAD


@pytest.mark.parametrize(
    "script",
    [p for p in _scripts(*SCRIPT_DIRS) if p.name != "common.sh"],
    ids=lambda p: str(p.relative_to(LAB_ROOT)),
)
def test_no_bare_kubectl_or_docker(script):
    for n, line in enumerate(script.read_text().splitlines(), 1):
        code = line.split("#", 1)[0] if not line.lstrip().startswith("#!") else ""
        assert not BARE_TOOL.search(code), f"line {n}: use k / dk / dc instead: {line.strip()}"


def test_mission_commands_are_non_interactive(catalog):
    for mission in catalog.missions.values():
        for step in mission.steps:
            assert step.command.strip(), f"{mission.id}.{step.id}: empty command"
            assert not INTERACTIVE.search(step.command), f"{mission.id}.{step.id}: {step.command}"


def test_scenario_names_do_not_reveal_tags(catalog):
    for s in catalog.scenarios.values():
        public = f"{s.id} {s.title} {s.symptom}".lower()
        for tag in s.tags:
            assert tag.lower() not in public, f"{s.id}: '{tag}' appears in id/title/symptom"


def test_every_reset_ends_with_restore(catalog):
    for sid in catalog.scenarios:
        last = (catalog.paths[sid] / "reset.sh").read_text().strip().splitlines()[-1]
        assert 'environment/restore.sh"' in last, sid
