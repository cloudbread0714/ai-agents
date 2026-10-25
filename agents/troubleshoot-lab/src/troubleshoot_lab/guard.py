"""Python side of the sandbox guard (research R3). ``lib/common.sh`` repeats the same checks.

Readiness is checked before locality so that "you have not run ``make up``" is never
reported as "this is not the local sandbox".
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

CONTEXT = "kind-troubleshoot-lab"
_LOCAL_SERVER = re.compile(r"^https://127\.0\.0\.1:\d+$")
MAKE_UP = "make -C agents/troubleshoot-lab up"

Run = Callable[[list[str]], subprocess.CompletedProcess]
Which = Callable[[str], str | None]


class EnvNotReady(Exception):
    """Exit code 5: the practice environment is not up."""


class SandboxError(Exception):
    """Exit code 3: the configuration points somewhere other than the local sandbox."""


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)


def kubeconfig_path(lab_root: Path) -> Path:
    return lab_root / "environment" / ".kube" / "config"


def check_kind(lab_root: Path, *, run: Run = _run, which: Which = shutil.which) -> None:
    if which("kubectl") is None:
        raise EnvNotReady("kubectl이 없어요. make -C agents/troubleshoot-lab doctor 로 확인하세요")
    path = kubeconfig_path(lab_root)
    if not path.is_file():
        raise EnvNotReady(f"kind 클러스터가 준비되지 않았어요. {MAKE_UP} 을 먼저 실행하세요")
    base = ["kubectl", "--kubeconfig", str(path)]
    ctx = run([*base, "config", "current-context"])
    if ctx.returncode != 0:
        raise EnvNotReady(f"전용 kubeconfig를 읽을 수 없어요. {MAKE_UP} 을 다시 실행하세요")
    if ctx.stdout.strip() != CONTEXT:
        raise SandboxError(
            f"로컬 샌드박스가 아니에요: context가 {CONTEXT} 가 아니라 {ctx.stdout.strip()} 예요"
        )
    server = run(
        [*base, "config", "view", "--minify", "-o", "jsonpath={.clusters[0].cluster.server}"]
    )
    if not _LOCAL_SERVER.match(server.stdout.strip()):
        raise SandboxError(
            f"로컬 샌드박스가 아니에요: API 서버가 127.0.0.1이 아니라 {server.stdout.strip()} 예요"
        )
    if run([*base, "--context", CONTEXT, "get", "--raw", "/readyz"]).returncode != 0:
        raise EnvNotReady(f"kind 클러스터가 응답하지 않아요. {MAKE_UP} 을 실행하세요")


def check_docker(
    *, env: Mapping[str, str] | None = None, run: Run = _run, which: Which = shutil.which
) -> None:
    env = os.environ if env is None else env
    if which("docker") is None:
        raise EnvNotReady("docker가 없어요. make -C agents/troubleshoot-lab doctor 로 확인하세요")
    host = env.get("DOCKER_HOST", "")
    if host and not host.startswith("unix://"):
        raise SandboxError(f"로컬 샌드박스가 아니에요: DOCKER_HOST={host}")
    endpoint = run(["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"])
    value = endpoint.stdout.strip() if endpoint.returncode == 0 else ""
    if value and not value.startswith("unix://"):
        raise SandboxError(f"로컬 샌드박스가 아니에요: docker context 엔드포인트가 {value} 예요")
    if run(["docker", "info"]).returncode != 0:
        raise EnvNotReady(
            f"Docker가 실행 중이 아니에요. Docker Desktop을 켠 뒤 {MAKE_UP} 을 실행하세요"
        )


def check_for(
    env_name: str,
    lab_root: Path,
    *,
    env: Mapping[str, str] | None = None,
    run: Run = _run,
    which: Which = shutil.which,
) -> None:
    """Check the side of the environment (``compose`` or ``kind``) an item runs in."""
    if env_name == "kind":
        check_kind(lab_root, run=run, which=which)
    else:
        check_docker(env=env, run=run, which=which)


def restore_mode(env_name: str) -> str:
    return "kind" if env_name == "kind" else "compose"
