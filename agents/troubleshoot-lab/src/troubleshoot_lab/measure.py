"""One measurement: k6 load + container resource sampling (contracts/measurement.md, R20).

Only measured values are recorded. Anything that could not be collected becomes a status
(`unavailable`, `not_applicable`, `skipped`); no code path fills in a default, an estimate
or a previous value (FR-017, SC-004).
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from troubleshoot_lab.guard import CONTEXT, kubeconfig_path
from troubleshoot_lab.models import METRIC_KEYS, Scenario

K6_IMAGE = "grafana/k6:1.0.0"
COMPOSE_NETWORK = "troubleshoot-lab_lab"
KIND_NETWORK = "kind"
KIND_TARGET = "http://troubleshoot-lab-control-plane:30080"
OK_DURATION = "http_req_duration{expected_response:true}"

Cmd = Callable[[list[str], float], subprocess.CompletedProcess]
Metrics = dict[str, dict[str, Any]]


class MeasureError(Exception):
    """The measurement could not run; nothing is recorded."""


def _run(cmd: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def target_url(scenario: Scenario) -> str:
    spec = scenario.measure
    if scenario.env == "kind":
        base = KIND_TARGET
    elif spec.scheme == "https":
        base = "https://nginx:443"
    else:
        base = "http://nginx"
    return base + spec.path


def container_name(service: str) -> str:
    return f"troubleshoot-lab-{service}-1"


def _value(v: float) -> dict[str, Any]:
    return {"value": round(float(v), 3)}


def _status(s: str) -> dict[str, Any]:
    return {"status": s}


def skipped() -> Metrics:
    return {key: _status("skipped") for key in METRIC_KEYS}


def parse_summary(data: dict[str, Any]) -> Metrics:
    """Latency, throughput and errors from a k6 ``handleSummary`` JSON."""
    m = data.get("metrics", {})
    reqs = m.get("http_reqs", {}).get("values", {})
    count = int(reqs.get("count", 0))
    failed = m.get("http_req_failed", {}).get("values", {})
    out: Metrics = {"requests": _value(count), "rps": _value(reqs.get("rate", 0.0))}
    if count == 0:
        out["error_rate"] = _status("not_applicable")
    else:
        out["error_rate"] = _value(failed.get("rate", 0.0))
    ok = m.get(OK_DURATION, {}).get("values", {})
    successes = count - int(failed.get("passes", 0))  # http_req_failed "passes" = failed requests
    if successes > 0 and "avg" in ok and "p(95)" in ok:
        out["avg_ms"] = _value(ok["avg"])
        out["p95_ms"] = _value(ok["p(95)"])
    else:
        out["avg_ms"] = out["p95_ms"] = _status("not_applicable")
    return out


_DOCKER_STATS = re.compile(r"^\s*([\d.]+)%\s+([\d.]+)\s*([KMG]i?B)")
_UNIT_MIB = {"KiB": 1 / 1024, "KB": 1 / 1024, "MiB": 1, "MB": 1, "GiB": 1024, "GB": 1024}


def parse_docker_stats(line: str) -> tuple[float, float] | None:
    """``"12.50% 61.3MiB / 7.6GiB"`` -> (cpu %, mem MiB)."""
    match = _DOCKER_STATS.match(line)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2)) * _UNIT_MIB[match.group(3)]


def parse_kubectl_top(output: str) -> tuple[float, float] | None:
    """Sum of ``kubectl top pod --no-headers`` rows -> (cpu % of one core, mem MiB)."""
    cpu = mem = 0.0
    rows = 0
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        cpu_s, mem_s = parts[1], parts[2]
        cpu += float(cpu_s[:-1]) / 10 if cpu_s.endswith("m") else float(cpu_s) * 100
        mem += (
            float(mem_s[:-2]) * (1024 if mem_s.endswith("Gi") else 1) if mem_s.endswith("i") else 0
        )
        rows += 1
    return (cpu, mem) if rows else None


def resource_metrics(samples: list[tuple[float, float]]) -> Metrics:
    if not samples:
        return {k: _status("unavailable") for k in ("cpu_avg_pct", "cpu_max_pct", "mem_max_mib")}
    cpus = [c for c, _ in samples]
    return {
        "cpu_avg_pct": _value(sum(cpus) / len(cpus)),
        "cpu_max_pct": _value(max(cpus)),
        "mem_max_mib": _value(max(m for _, m in samples)),
    }


class Measurer:
    def __init__(
        self,
        lab_root: Path,
        *,
        guard: Callable[[str], None],
        cmd: Cmd = _run,
        sample_every: float = 1.0,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.lab_root = lab_root
        self.guard = guard
        self.cmd = cmd
        self.sample_every = sample_every
        self.now = now

    def _k6_command(self, scenario: Scenario, out: Path) -> list[str]:
        spec = scenario.measure
        net = KIND_NETWORK if scenario.env == "kind" else COMPOSE_NETWORK
        cmd = ["docker", "run", "--rm", "--network", net, "-v", f"{out}:/out"]
        cmd += ["-v", f"{self.lab_root / 'environment' / 'k6'}:/scripts:ro"]
        if spec.scheme == "https":
            certs = self.lab_root / ".lab-state" / "certs"
            cmd += ["-v", f"{certs}:/certs:ro", "-e", "SSL_CERT_FILE=/certs/ca.pem"]
        cmd += ["-e", f"TARGET_URL={target_url(scenario)}", "-e", f"METHOD={spec.method}"]
        cmd += ["-e", f"VUS={spec.vus}", "-e", f"DURATION={spec.duration_s}s"]
        if spec.body:
            cmd += ["-e", f"BODY={spec.body}"]
        return [*cmd, K6_IMAGE, "run", "--quiet", "/scripts/measure.js"]

    def _sample_once(self, scenario: Scenario) -> tuple[float, float] | None:
        service = scenario.measure.service
        if scenario.env == "kind":
            kc = str(kubeconfig_path(self.lab_root))
            res = self.cmd(
                [
                    "kubectl",
                    "--kubeconfig",
                    kc,
                    "--context",
                    CONTEXT,
                    "-n",
                    "lab",
                    "top",
                    "pod",
                    "-l",
                    f"app={service}",
                    "--no-headers",
                ],
                15,
            )
            return parse_kubectl_top(res.stdout) if res.returncode == 0 else None
        res = self.cmd(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "{{.CPUPerc}} {{.MemUsage}}",
                container_name(service),
            ],
            15,
        )
        return parse_docker_stats(res.stdout.strip()) if res.returncode == 0 else None

    def run(self, scenario: Scenario, attempt: int, phase: str) -> Metrics:
        self.guard(scenario.env)
        stamp = self.now().strftime("%Y%m%dT%H%M%S")
        out = self.lab_root / ".lab-state" / "measure" / f"{scenario.id}-{attempt}-{phase}-{stamp}"
        out.mkdir(parents=True, exist_ok=True)
        samples: list[tuple[float, float]] = []
        stop = threading.Event()

        def sampler() -> None:
            while not stop.is_set():
                try:
                    sample = self._sample_once(scenario)
                except (subprocess.TimeoutExpired, OSError):
                    sample = None
                if sample is not None:
                    samples.append(sample)
                stop.wait(self.sample_every)

        thread = threading.Thread(target=sampler, daemon=True)
        thread.start()
        started = time.monotonic()
        try:
            res = self.cmd(self._k6_command(scenario, out), scenario.measure.duration_s + 20)
        except subprocess.TimeoutExpired:
            raise MeasureError("k6 측정이 제한 시간 안에 끝나지 않았어요") from None
        finally:
            stop.set()
            thread.join(timeout=20)
        if res.returncode not in (0, 99):  # 99 = thresholds crossed, results still valid
            raise MeasureError(
                f"k6 실행 실패(종료 코드 {res.returncode}): {res.stderr.strip()[-300:]}"
            )
        summary = out / "summary.json"
        if not summary.exists():
            raise MeasureError("k6 결과 파일을 찾을 수 없어요")
        result = parse_summary(json.loads(summary.read_text(encoding="utf-8")))
        result.update(resource_metrics(samples))
        result["_elapsed_s"] = {"value": round(time.monotonic() - started, 1)}  # display only
        return result


# --- display (contracts/measurement.md 출력) ---------------------------------------------

ROWS: tuple[tuple[str, str, str], ...] = (
    ("평균 응답 시간", "avg_ms", "ms"),
    ("p95 응답 시간", "p95_ms", "ms"),
    ("처리량", "rps", "req/s"),
    ("오류율", "error_rate", "%"),
    ("CPU 평균", "cpu_avg_pct", "%"),
    ("CPU 최대", "cpu_max_pct", "%"),
    ("메모리 최대", "mem_max_mib", "MiB"),
)
STATUS_LABEL = {"unavailable": "측정 불가", "skipped": "측정 생략", "not_applicable": "해당 없음"}


def cell(metric: dict[str, Any] | None, key: str, skip_reason: str | None = None) -> str:
    if metric is None:
        return "측정하지 않음"
    if "status" in metric and metric["status"] is not None:
        label = STATUS_LABEL[metric["status"]]
        return f"{label}({skip_reason})" if metric["status"] == "skipped" and skip_reason else label
    value = metric["value"] * (100 if key == "error_rate" else 1)
    return f"{value:.1f}"


def _number(metric: dict[str, Any] | None) -> float | None:
    if metric and metric.get("value") is not None:
        return float(metric["value"])
    return None


def format_table(
    metrics: Metrics, baseline: Metrics | None = None, skip_reason: str | None = None
) -> str:
    header = "| 지표 | 값 |" + (" 정상 대비 |" if baseline else "")
    lines = [header, "|------|----|" + ("------|" if baseline else "")]
    for label, key, unit in ROWS:
        value = cell(metrics.get(key), key, skip_reason)
        shown = f"{value} {unit}" if value[0].isdigit() else value
        row = f"| {label} | {shown} |"
        if baseline is not None:
            now, base = _number(metrics.get(key)), _number(baseline.get(key))
            # compare only when both sides are measured values
            row += f" {'×' + format(now / base, '.1f') if now is not None and base else '—'} |"
        lines.append(row)
    return "\n".join(lines)


def strip_display(metrics: Metrics) -> Metrics:
    return {k: v for k, v in metrics.items() if k in METRIC_KEYS}


def fault_signals(baseline: Metrics, fault: Metrics) -> list[str]:
    """Which SC-005 criteria a fault measurement meets against its baseline (empty: none)."""
    signals = []
    base_err, err = _number(baseline.get("error_rate")), _number(fault.get("error_rate"))
    if base_err is not None and err is not None and err - base_err >= 0.05:
        signals.append("error_rate")
    for key in ("avg_ms", "p95_ms"):
        base, now = _number(baseline.get(key)), _number(fault.get(key))
        if base is not None and (fault.get(key) or {}).get("status") == "not_applicable":
            signals.append(f"{key}:not_applicable")
        elif base and now is not None and (now >= base * 1.5 or now <= base / 1.5):
            signals.append(key)
    base_cpu, cpu = _number(baseline.get("cpu_max_pct")), _number(fault.get("cpu_max_pct"))
    if base_cpu is not None and cpu is not None and cpu - base_cpu >= 20:
        signals.append("cpu_max_pct")
    base_mem, mem = _number(baseline.get("mem_max_mib")), _number(fault.get("mem_max_mib"))
    if base_mem and mem is not None and mem >= base_mem * 1.3:
        signals.append("mem_max_mib")
    return signals
