import pytest

from troubleshoot_lab import runner as runner_mod
from troubleshoot_lab.guard import EnvNotReady, SandboxError
from troubleshoot_lab.runner import ScriptRunner


def _item(tmp_path, body):
    d = tmp_path / "items" / "x"
    d.mkdir(parents=True)
    script = d / "verify.sh"
    script.write_text(f"#!/usr/bin/env bash\n{body}\n")
    script.chmod(0o755)
    return d


def test_contract_environment_cwd_and_args(tmp_path):
    fields = "$LAB_ROOT|$LAB_STATE|$LAB_WORK|$LAB_ITEM_DIR|$LAB_ITEM_ID|$KUBECONFIG"
    d = _item(tmp_path, f'echo "{fields}|$COMPOSE_PROJECT_NAME|$PWD|$*"')
    r = ScriptRunner(tmp_path, environ={"PATH": "/usr/bin:/bin"})
    assert r.run("x", d, "verify.sh", "step-1", "tok") == 0
    log = next((tmp_path / ".lab-state" / "logs").iterdir()).read_text()
    root, state, work, item_dir, item_id, kube, project, cwd, args = log.strip().split("|")
    assert root == str(tmp_path)
    assert state == str(tmp_path / ".lab-state")
    assert work == str(tmp_path / ".lab-state" / "work")
    assert item_dir == str(d)
    assert cwd in (str(d), str(d.resolve()))
    assert item_id == "x"
    assert kube == str(tmp_path / "environment" / ".kube" / "config")
    assert project == "troubleshoot-lab"
    assert args == "step-1 tok"


def test_output_goes_only_to_log(tmp_path, capfd):
    d = _item(tmp_path, "echo SECRET-CAUSE; exit 1")
    assert ScriptRunner(tmp_path, environ={"PATH": "/usr/bin:/bin"}).run("x", d, "verify.sh") == 1
    assert "SECRET-CAUSE" not in capfd.readouterr().out
    assert "SECRET-CAUSE" in next((tmp_path / ".lab-state" / "logs").iterdir()).read_text()


@pytest.mark.parametrize("code,exc", [(3, SandboxError), (5, EnvNotReady)])
def test_guard_exit_codes_raise_with_message(tmp_path, code, exc):
    d = _item(tmp_path, f'echo "lab: 이유 메시지" >&2; exit {code}')
    with pytest.raises(exc, match="이유 메시지"):
        ScriptRunner(tmp_path, environ={"PATH": "/usr/bin:/bin"}).run("x", d, "verify.sh")


def test_timeout_maps_to_124(tmp_path, monkeypatch):
    monkeypatch.setitem(runner_mod.TIMEOUTS, "verify.sh", 0.2)
    d = _item(tmp_path, "sleep 5")
    assert ScriptRunner(tmp_path, environ={"PATH": "/usr/bin:/bin"}).run("x", d, "verify.sh") == 124


def test_timeouts_contract():
    assert runner_mod.TIMEOUTS["verify.sh"] == 60
    assert runner_mod.TIMEOUTS["inject.sh"] == runner_mod.TIMEOUTS["setup.sh"] == 300
    assert runner_mod.TIMEOUTS["reset.sh"] == 300


def test_mark_dirty_by_env(tmp_path):
    r = ScriptRunner(tmp_path, environ={})
    r.mark_dirty("kind")
    r.mark_dirty("compose")
    assert (tmp_path / ".lab-state" / "dirty-kind").exists()
    assert (tmp_path / ".lab-state" / "dirty-compose").exists()
