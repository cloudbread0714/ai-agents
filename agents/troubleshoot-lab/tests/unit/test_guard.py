import subprocess

import pytest

from troubleshoot_lab.guard import (
    CONTEXT,
    EnvNotReady,
    SandboxError,
    check_docker,
    check_for,
    check_kind,
    kubeconfig_path,
)


def fake_run(responses):
    """responses: list of (substring of the joined command, returncode, stdout)."""
    calls = []

    def run(cmd):
        joined = " ".join(cmd)
        calls.append(joined)
        for needle, code, out in responses:
            if needle in joined:
                return subprocess.CompletedProcess(cmd, code, out, "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    run.calls = calls
    return run


def have(*tools):
    return lambda name: f"/usr/bin/{name}" if name in tools else None


@pytest.fixture
def kube_root(tmp_path):
    path = kubeconfig_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("apiVersion: v1\n")
    return tmp_path


KIND_OK = [
    ("current-context", 0, CONTEXT + "\n"),
    ("view --minify", 0, "https://127.0.0.1:52344"),
    ("/readyz", 0, "ok"),
]


def test_kind_ok(kube_root):
    run = fake_run(KIND_OK)
    check_kind(kube_root, run=run, which=have("kubectl"))
    assert all(f"--kubeconfig {kubeconfig_path(kube_root)}" in c for c in run.calls)


def test_kind_missing_tool_or_kubeconfig_is_not_ready(tmp_path, kube_root):
    with pytest.raises(EnvNotReady):
        check_kind(kube_root, run=fake_run(KIND_OK), which=have())
    with pytest.raises(EnvNotReady, match="make -C agents/troubleshoot-lab up"):
        check_kind(tmp_path / "nothing", run=fake_run(KIND_OK), which=have("kubectl"))


def test_kind_unreadable_kubeconfig_or_unreachable_cluster_is_not_ready(kube_root):
    with pytest.raises(EnvNotReady):
        check_kind(kube_root, run=fake_run([("current-context", 1, "")]), which=have("kubectl"))
    with pytest.raises(EnvNotReady, match="응답하지"):
        check_kind(kube_root, run=fake_run([("/readyz", 1, ""), *KIND_OK]), which=have("kubectl"))


def test_kind_wrong_context_is_refused(kube_root):
    run = fake_run([("current-context", 0, "prod-cluster"), *KIND_OK])
    with pytest.raises(SandboxError, match="prod-cluster"):
        check_kind(kube_root, run=run, which=have("kubectl"))


@pytest.mark.parametrize("server", ["https://10.0.0.5:6443", "https://127.0.0.1.evil:1", ""])
def test_kind_remote_server_is_refused(kube_root, server):
    run = fake_run([("view --minify", 0, server), *KIND_OK])
    with pytest.raises(SandboxError):
        check_kind(kube_root, run=run, which=have("kubectl"))


DOCKER_OK = [("context inspect", 0, "unix:///var/run/docker.sock"), ("docker info", 0, "")]


def test_docker_ok_with_unix_socket():
    check_docker(
        env={"DOCKER_HOST": "unix:///tmp/d.sock"}, run=fake_run(DOCKER_OK), which=have("docker")
    )


def test_docker_remote_host_or_context_is_refused():
    with pytest.raises(SandboxError, match="DOCKER_HOST"):
        check_docker(
            env={"DOCKER_HOST": "tcp://10.0.0.1:2375"},
            run=fake_run(DOCKER_OK),
            which=have("docker"),
        )
    remote = fake_run([("context inspect", 0, "ssh://user@host"), ("docker info", 0, "")])
    with pytest.raises(SandboxError, match="ssh://"):
        check_docker(env={}, run=remote, which=have("docker"))


def test_docker_not_running_or_missing_is_not_ready():
    with pytest.raises(EnvNotReady, match="Docker가 실행 중이 아니에요"):
        check_docker(
            env={}, run=fake_run([("docker info", 1, ""), *DOCKER_OK]), which=have("docker")
        )
    with pytest.raises(EnvNotReady):
        check_docker(env={}, run=fake_run(DOCKER_OK), which=have())


def test_check_for_dispatches_by_category(kube_root):
    run = fake_run([*KIND_OK, *DOCKER_OK])
    check_for("kind", kube_root, run=run, which=have("kubectl"))
    assert any("kubectl" in c for c in run.calls)
    run = fake_run(DOCKER_OK)
    check_for("compose", kube_root, env={}, run=run, which=have("docker"))
    assert all(c.startswith("docker") for c in run.calls)
