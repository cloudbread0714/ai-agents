"""Each mission step fails before the documented command and passes after it (research R5, U3)."""

from pathlib import Path

import pytest

from troubleshoot_lab.catalog import load_catalog
from troubleshoot_lab.guard import restore_mode

pytestmark = pytest.mark.sandbox

MISSION_IDS = sorted(load_catalog(Path(__file__).resolve().parents[2]).missions)


@pytest.mark.parametrize("mission_id", MISSION_IDS)
def test_mission_steps(sandbox, mission_id):
    mission = sandbox.catalog.missions[mission_id]
    item_dir = sandbox.catalog.paths[mission_id]
    mode = restore_mode(mission.category)
    run = sandbox.runner.run

    assert sandbox.runner.restore(mode) == 0
    baseline = sandbox.fingerprint(mode)
    sandbox.runner.mark_dirty(mission.category)
    assert run(mission_id, item_dir, "setup.sh") == 0

    for step in mission.steps:
        wrong = ["__wrong__"] if step.check == "answer" else []
        assert run(mission_id, item_dir, "verify.sh", step.id, *wrong) != 0, (
            f"{step.id} passed early"
        )

        result = sandbox.shell(step.command)
        assert result.returncode == 0, f"{step.id}: command failed: {result.stderr[-500:]}"

        args = [step.id]
        if step.check == "answer":
            args.append(sandbox.answers(mission_id).get(step.id) or result.stdout)
        assert run(mission_id, item_dir, "verify.sh", *args) == 0, f"{step.id} did not pass"

    assert sandbox.runner.restore(mode) == 0
    assert sandbox.healthcheck(mode) == 0
    assert sandbox.fingerprint(mode) == baseline, "mission state was not cleaned up by restore"
