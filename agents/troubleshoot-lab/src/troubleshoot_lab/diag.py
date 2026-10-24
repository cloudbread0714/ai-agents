"""Run diagnostic commands inside the toolbox container attached to a target (research R21).

The macOS host lacks ``ss``, ``free``, ``vmstat``…; the toolbox joins the target's network
and PID namespaces so the output describes that service. Output is shown as is: the learner
asked for it and is doing the analysis (unlike verify scripts, whose output stays hidden).
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from troubleshoot_lab.guard import CONTEXT, kubeconfig_path
from troubleshoot_lab.measure import container_name

TOOLBOX = "lab-toolbox:dev"
SERVICES = ("nginx", "api", "ext", "redis", "postgres")

Cmd = Callable[[list[str], float], subprocess.CompletedProcess]


def _run(cmd: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def _other(service: str) -> str:
    """A different service on the same network to diagnose from."""
    return "nginx" if service != "nginx" else "api"


@dataclass
class DiagResult:
    outcome: str  # ok | target_down | unknown_service | timeout
    exit_code: int
    output: str


class Diagnoser:
    def __init__(self, lab_root: Path, *, guard: Callable[[str], None], cmd: Cmd = _run):
        self.lab_root = lab_root
        self.guard = guard
        self.cmd = cmd

    def _kubectl(self) -> list[str]:
        return [
            "kubectl",
            "--kubeconfig",
            str(kubeconfig_path(self.lab_root)),
            "--context",
            CONTEXT,
        ]

    def _pod(self, service: str) -> str | None:
        res = self.cmd(
            [
                *self._kubectl(),
                "-n",
                "lab",
                "get",
                "pods",
                "-l",
                f"app={service}",
                "--field-selector=status.phase=Running",
                "-o",
                "jsonpath={.items[0].metadata.name}",
            ],
            20,
        )
        name = res.stdout.strip() if res.returncode == 0 else ""
        return name or None

    def exec(self, service: str, command: str, env_name: str) -> DiagResult:
        if service not in SERVICES:
            return DiagResult(
                "unknown_service",
                2,
                f"'{service}'은(는) 없는 서비스예요. 가능한 값: {', '.join(SERVICES)}",
            )
        self.guard(env_name)
        if env_name == "kind":
            pod = self._pod(service)
            if pod is None:
                return self._down(service, _other(service))
            argv = [
                *self._kubectl(),
                "debug",
                "-n",
                "lab",
                pod,
                f"--image={TOOLBOX}",
                f"--target={service}",
                "--attach",
                "--quiet",
                "--",
                "sh",
                "-c",
                command,
            ]
        else:
            name = container_name(service)
            state = self.cmd(["docker", "inspect", "-f", "{{.State.Running}}", name], 20)
            if state.returncode != 0 or state.stdout.strip() != "true":
                return self._down(service, _other(service))
            argv = [
                "docker",
                "run",
                "--rm",
                "--network",
                f"container:{name}",
                "--pid",
                f"container:{name}",
                TOOLBOX,
                "sh",
                "-c",
                command,
            ]
        try:
            res = self.cmd(argv, 120)
        except subprocess.TimeoutExpired:
            return DiagResult("timeout", 1, "명령이 120초 안에 끝나지 않았어요.")
        return DiagResult("ok", res.returncode, (res.stdout + res.stderr).rstrip())

    @staticmethod
    def _down(service: str, other: str) -> DiagResult:
        return DiagResult(
            "target_down",
            1,
            f"대상 서비스 '{service}'가 실행 중이 아니에요. 컨테이너 상태와 로그부터 확인하거나 "
            f"(docker compose ps -a, docker compose logs {service}), "
            f"같은 네트워크의 다른 서비스에서 진단해 보세요: /lab-exec {other} <명령>",
        )

    def shell(self, service: str, env_name: str) -> str:
        if env_name == "kind":
            kc = shlex.quote(str(kubeconfig_path(self.lab_root)))
            return (
                f"kubectl --kubeconfig {kc} --context {CONTEXT} -n lab debug -it "
                f"$(kubectl --kubeconfig {kc} --context {CONTEXT} -n lab get pods -l app={service} "
                f"-o jsonpath='{{.items[0].metadata.name}}') "
                f"--image={TOOLBOX} --target={service} -- bash"
            )
        name = container_name(service)
        return (
            f"docker run --rm -it --network container:{name} --pid container:{name} {TOOLBOX} bash"
        )
