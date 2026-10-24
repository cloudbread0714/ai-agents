import subprocess

import pytest

from troubleshoot_lab.diag import TOOLBOX, Diagnoser
from troubleshoot_lab.guard import EnvNotReady


class FakeCmd:
    def __init__(self, running="true", pod="api-abc"):
        self.calls = []
        self.running = running
        self.pod = pod

    def __call__(self, cmd, timeout):
        self.calls.append(cmd)
        if cmd[:2] == ["docker", "inspect"]:
            code = 0 if self.running is not None else 1
            return subprocess.CompletedProcess(cmd, code, self.running or "", "")
        if "get" in cmd and "pods" in cmd:
            return subprocess.CompletedProcess(cmd, 0, self.pod or "", "")
        return subprocess.CompletedProcess(cmd, 0, "LISTEN 0 128 0.0.0.0:8000\n", "")


def test_compose_exec_attaches_to_network_and_pid_without_extra_caps(tmp_path):
    guard, cmd = [], FakeCmd()
    result = Diagnoser(tmp_path, guard=guard.append, cmd=cmd).exec("api", "ss -lntp", "compose")
    assert guard == ["compose"]
    argv = cmd.calls[-1]
    assert argv == [
        "docker", "run", "--rm", "--network", "container:troubleshoot-lab-api-1",
        "--pid", "container:troubleshoot-lab-api-1", TOOLBOX, "sh", "-c", "ss -lntp",
    ]
    assert "--cap-add" not in argv
    assert (result.outcome, result.exit_code) == ("ok", 0)
    assert "0.0.0.0:8000" in result.output


def test_kind_exec_uses_ephemeral_debug_container(tmp_path):
    cmd = FakeCmd()
    Diagnoser(tmp_path, guard=lambda e: None, cmd=cmd).exec("api", "top -b -n 1", "kind")
    argv = cmd.calls[-1]
    assert argv[argv.index("debug") + 3] == "api-abc"
    assert f"--image={TOOLBOX}" in argv and "--target=api" in argv and "--attach" in argv
    assert argv[-3:] == ["sh", "-c", "top -b -n 1"]


@pytest.mark.parametrize("env,kw", [("compose", {"running": "false"}), ("compose", {"running": None}), ("kind", {"pod": ""})])
def test_stopped_target_is_reported(tmp_path, env, kw):
    result = Diagnoser(tmp_path, guard=lambda e: None, cmd=FakeCmd(**kw)).exec("nginx", "ss", env)
    assert result.outcome == "target_down" and "실행 중이 아니에요" in result.output
    assert "/lab-exec api" in result.output  # suggests another service


def test_unknown_service_and_guard(tmp_path):
    d = Diagnoser(tmp_path, guard=lambda e: None, cmd=FakeCmd())
    assert d.exec("mysql", "ls", "compose").exit_code == 2

    def refuse(env):
        raise EnvNotReady("make up")

    with pytest.raises(EnvNotReady):
        Diagnoser(tmp_path, guard=refuse, cmd=FakeCmd()).exec("api", "ls", "compose")


def test_shell_prints_interactive_command_only(tmp_path):
    cmd = FakeCmd()
    text = Diagnoser(tmp_path, guard=lambda e: None, cmd=cmd).shell("redis", "compose")
    assert text.startswith("docker run --rm -it --network container:troubleshoot-lab-redis-1")
    assert cmd.calls == []
    assert "debug -it" in Diagnoser(tmp_path, guard=lambda e: None, cmd=cmd).shell("api", "kind")
