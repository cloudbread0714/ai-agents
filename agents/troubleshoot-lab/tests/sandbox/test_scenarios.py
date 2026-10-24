"""Scenario cycle: inject, verify fails, reset twice, back to the pre-inject state."""

import time
from pathlib import Path

import pytest

from troubleshoot_lab.catalog import load_catalog
from troubleshoot_lab.guard import restore_mode

pytestmark = pytest.mark.sandbox

SCENARIO_IDS = sorted(load_catalog(Path(__file__).resolve().parents[2]).scenarios)

INJECT_LIMIT_SECONDS = 180  # SC-004


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_inject_verify_reset_cycle(sandbox, scenario_id):
    scenario = sandbox.catalog.scenarios[scenario_id]
    item_dir = sandbox.catalog.paths[scenario_id]
    mode = restore_mode(scenario.category)
    run = sandbox.runner.run

    assert sandbox.runner.restore(mode) == 0
    baseline = sandbox.fingerprint(mode)

    sandbox.runner.mark_dirty(scenario.category)
    started = time.monotonic()
    assert run(scenario_id, item_dir, "inject.sh") == 0
    assert time.monotonic() - started < INJECT_LIMIT_SECONDS

    assert run(scenario_id, item_dir, "verify.sh") != 0, (
        "verify passed with the fault still in place"
    )

    assert run(scenario_id, item_dir, "reset.sh") == 0
    assert sandbox.healthcheck(mode) == 0
    assert run(scenario_id, item_dir, "reset.sh") == 0, "reset is not idempotent"
    assert sandbox.healthcheck(mode) == 0
    assert sandbox.fingerprint(mode) == baseline, "reset did not return to the pre-inject state"
