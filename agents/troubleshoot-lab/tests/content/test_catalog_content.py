"""Static checks on the real catalog (research R13 정적). No Docker or network needed."""

import os
import re
import subprocess
from pathlib import Path

import pytest

from troubleshoot_lab.catalog import load_catalog
from troubleshoot_lab.models import FIELDS

LAB_ROOT = Path(__file__).resolve().parents[2]
CONTENT_DIRS = ("missions", "scenarios", "templates")
SCRIPT_DIRS = (*CONTENT_DIRS, "lib", "environment")
REQUIRED_HEAD = ["#!/usr/bin/env bash", "set -euo pipefail", 'source "$LAB_ROOT/lib/common.sh"']
# kubectl / docker / docker compose must go through k / dk / dc (lib/common.sh) so the guard runs.
BARE_TOOL = re.compile(r"(^|[\s;|&(`])(kubectl|docker)(\s|$)")
INTERACTIVE = re.compile(r"(\s-it\b|\s-ti\b|\bvi\b|\bvim\b|\bnano\b|\bless\b|\bmore\b)")

# Curriculum numbers every catalog must carry (spec FR-004).
FR004_NOS = {str(n) for n in range(1, 16)} | {"17", "18", "18-B", "19", "20"}
FR004_NOS |= {"extra-1", "extra-2", "extra-3"}

# FR-005: diagnostic commands and concepts the warmups as a whole must cover, per field.
# Case-insensitive regexes over each field's mission goals, guides and commands.
FR005_TOPICS = {
    "network": [
        r"curl -s?v",
        r"curl .*-w",
        r"\bdig\b",
        r"nslookup",
        r"\bnc -",
        r"ss -lntp",
        r"ss -s\b",
        r"ip addr",
        r"ip route",
        r"openssl s_client",
    ],
    "linux": [
        r"\btop\b",
        r"ps aux --sort",
        r"load average",
        r"free -h",
        r"vmstat 1",
        r"df -h",
        r"du -sh",
        r"ulimit -n",
        r"\blsof\b",
    ],
    "webserver": [r"ss -ant", r"established", r"time.wait", r"close.wait", r"\b502\b", r"\b504\b"],
    "db-cache": [r"pg_stat_activity", r"\bexplain\b", r"redis-cli", r"\binfo\b", r"\bttl\b", r"keyspace"],
    "lb-cloud": [r"endpoint", r"readiness"],
    "monitoring": [r"\bk6\b", r"p\(?95", r"\blogs\b", r"rollout"],
}
# Host macOS has none of these; hints must run them inside the toolbox via /lab-exec.
TOOLBOX_ONLY = re.compile(r"^(ss|free|vmstat|top|dig)\b")


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(LAB_ROOT)


def _scripts(*dirs):
    return sorted(p for d in dirs for p in (LAB_ROOT / d).rglob("*.sh"))


def test_catalog_and_plan_load_without_errors(catalog):
    assert catalog.errors == []
    assert catalog.plan is not None
    assert len(catalog.scenarios) >= 23


def test_all_six_fields_are_used(catalog):
    assert {s.fields[0] for s in catalog.scenarios.values()} == set(FIELDS)


def test_fr004_curriculum_numbers_present(catalog):
    assert {s.curriculum_no for s in catalog.scenarios.values()} >= FR004_NOS


def test_measure_paths_are_internal(catalog):
    for s in catalog.scenarios.values():
        assert s.measure.path.startswith("/"), s.id
        assert "://" not in s.measure.path and "localhost" not in s.measure.path, s.id


def test_interview_questions(catalog):
    for s in catalog.scenarios.values():
        assert 1 <= len(s.interview) <= 2, s.id


def test_plan_covers_every_scenario(catalog):
    planned = set(catalog.plan.extras)
    for day in catalog.plan.days:
        planned |= set(day.items or day.pool or [])
    assert set(catalog.scenarios) <= planned


def _mission_text(catalog, field):
    parts = []
    for m in catalog.missions.values():
        if m.field == field:
            parts += m.goals + [f"{st.guide} {st.command}" for st in m.steps]
    return "\n".join(parts)


@pytest.mark.parametrize("field", list(FR005_TOPICS))
def test_fr005_warmup_topics_covered(catalog, field):
    text = _mission_text(catalog, field)
    missing = [t for t in FR005_TOPICS[field] if not re.search(t, text, re.I)]
    assert not missing, f"{field}: no warmup covers {missing}"


def test_hints_run_toolbox_commands_through_lab_exec(catalog):
    for sid, hints in catalog.hints.items():
        for n, hint in enumerate(hints, 1):
            for line in hint.splitlines():
                assert not TOOLBOX_ONLY.match(line.strip()), (
                    f"{sid} hint {n}: use /lab-exec: {line}"
                )


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
