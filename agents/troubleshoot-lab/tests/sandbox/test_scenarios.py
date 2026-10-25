"""Scenario cycle against the real environment (T055).

restore → baseline measure → fingerprint → inject → verify fails → fault measure differs
measurably (SC-005) → reset twice → back to the pre-inject state.
"""

import time
from pathlib import Path

import pytest

from troubleshoot_lab.catalog import load_catalog
from troubleshoot_lab.guard import restore_mode
from troubleshoot_lab.learn import default_guard
from troubleshoot_lab.measure import Measurer, fault_signals

pytestmark = pytest.mark.sandbox

LAB_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_IDS = sorted(load_catalog(LAB_ROOT).scenarios)

INJECT_LIMIT_SECONDS = 180  # SC-004


@pytest.fixture(scope="module")
def measurer():
    return Measurer(LAB_ROOT, guard=default_guard(LAB_ROOT))


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_measure_inject_verify_reset_cycle(sandbox, measurer, scenario_id):
    scenario = sandbox.catalog.scenarios[scenario_id]
    item_dir = sandbox.catalog.paths[scenario_id]
    mode = restore_mode(scenario.env)
    run = sandbox.runner.run

    assert sandbox.runner.restore(mode) == 0
    baseline = measurer.run(scenario, 0, "baseline")
    assert baseline["error_rate"].get("value") == 0, f"baseline has errors: {baseline}"
    before = sandbox.fingerprint(mode)

    sandbox.runner.mark_dirty(scenario.env)
    started = time.monotonic()
    assert run(scenario_id, item_dir, "inject.sh") == 0
    assert time.monotonic() - started < INJECT_LIMIT_SECONDS

    assert run(scenario_id, item_dir, "verify.sh") != 0, (
        "verify passed with the fault still in place"
    )

    fault = measurer.run(scenario, 0, "fault")
    assert fault_signals(baseline, fault), (
        f"fault is not measurable (SC-005): baseline={baseline} fault={fault}"
    )

    assert run(scenario_id, item_dir, "reset.sh") == 0
    assert sandbox.healthcheck(mode) == 0
    assert run(scenario_id, item_dir, "reset.sh") == 0, "reset is not idempotent"
    assert sandbox.healthcheck(mode) == 0
    assert sandbox.fingerprint(mode) == before, "reset did not return to the pre-inject state"
