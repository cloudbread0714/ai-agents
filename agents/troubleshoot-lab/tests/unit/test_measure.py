import json
import os
import subprocess
from pathlib import Path

import pytest

from tl_support import scenario_spec
from troubleshoot_lab.measure import (
    K6_IMAGE,
    MeasureError,
    Measurer,
    fault_signals,
    format_table,
    parse_docker_stats,
    parse_kubectl_top,
    parse_summary,
    resource_metrics,
    skipped,
    target_url,
)
from troubleshoot_lab.models import Scenario

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "k6"


def _scenario(**kw) -> Scenario:
    spec = scenario_spec("s", **{k: v for k, v in kw.items() if k in ("env",)})
    spec["measure"].update(kw.get("measure", {}))
    return Scenario.model_validate(spec)


def test_parse_summary_ok():
    m = parse_summary(json.loads((FIXTURES / "summary_ok.json").read_text()))
    assert m["avg_ms"] == {"value": 12.4} and m["p95_ms"] == {"value": 30.1}  # successful only
    assert m["rps"] == {"value": 210.5} and m["requests"] == {"value": 4210}
    assert m["error_rate"] == {"value": 0.0}


def test_parse_summary_all_failed_is_not_applicable():
    m = parse_summary(json.loads((FIXTURES / "summary_all_failed.json").read_text()))
    assert m["avg_ms"] == m["p95_ms"] == {"status": "not_applicable"}
    assert m["error_rate"] == {"value": 1.0}


def test_parse_summary_zero_requests():
    m = parse_summary({"metrics": {"http_reqs": {"values": {"count": 0, "rate": 0}}}})
    assert m["error_rate"] == {"status": "not_applicable"}
    assert m["avg_ms"] == {"status": "not_applicable"}


def test_resource_parsers_and_unavailable():
    assert parse_docker_stats("12.50% 61.3MiB / 7.6GiB") == (12.5, 61.3)
    assert parse_docker_stats("0.00% 1.5GiB / 7GiB") == (0.0, 1536.0)
    assert parse_docker_stats("--") is None
    assert parse_kubectl_top("api-1 250m 60Mi\napi-2 1 1Gi\n") == (125.0, 1084.0)
    assert parse_kubectl_top("") is None
    assert resource_metrics([]) == {
        "cpu_avg_pct": {"status": "unavailable"},
        "cpu_max_pct": {"status": "unavailable"},
        "mem_max_mib": {"status": "unavailable"},
    }
    r = resource_metrics([(10.0, 50.0), (30.0, 70.0)])
    assert r["cpu_avg_pct"] == {"value": 20.0} and r["cpu_max_pct"] == {"value": 30.0}
    assert r["mem_max_mib"] == {"value": 70.0}


def test_skipped_marks_every_metric():
    assert all(v == {"status": "skipped"} for v in skipped().values())


@pytest.mark.parametrize(
    "env,measure,url",
    [
        ("compose", {"path": "/api/items"}, "http://nginx/api/items"),
        ("compose", {"path": "/healthz", "scheme": "https"}, "https://nginx:443/healthz"),
        ("kind", {"path": "/api/items"}, "http://troubleshoot-lab-control-plane:30080/api/items"),
    ],
)
def test_target_url_is_fixed_by_env(env, measure, url):
    assert target_url(_scenario(env=env, measure=measure)) == url


class FakeCmd:
    def __init__(self, tmp_path, summary="summary_ok.json", k6_code=0, stats="20.0% 50MiB / 1GiB"):
        self.calls = []
        self.summary = summary
        self.k6_code = k6_code
        self.stats = stats

    def __call__(self, cmd, timeout):
        self.calls.append((cmd, timeout))
        if K6_IMAGE in cmd:
            if self.k6_code == "timeout":
                raise subprocess.TimeoutExpired(cmd, timeout)
            out = Path(cmd[cmd.index("-v") + 1].split(":")[0])
            if self.summary:
                (out / "summary.json").write_text((FIXTURES / self.summary).read_text())
            return subprocess.CompletedProcess(cmd, self.k6_code, "", "boom")
        return subprocess.CompletedProcess(cmd, 0 if self.stats else 1, self.stats or "", "")


def test_measurer_runs_k6_on_the_lab_network_and_samples(tmp_path):
    guard = []
    cmd = FakeCmd(tmp_path)
    m = Measurer(tmp_path, guard=guard.append, cmd=cmd, sample_every=0.01)
    result = m.run(_scenario(), 1, "baseline")
    assert guard == ["compose"]
    k6 = next(c for c, _ in cmd.calls if K6_IMAGE in c)
    assert k6[k6.index("--network") + 1] == "troubleshoot-lab_lab"
    assert k6[k6.index("--user") + 1] == f"{os.getuid()}:{os.getgid()}"  # writable /out on Linux
    assert "TARGET_URL=http://nginx/api/items" in k6 and "VUS=2" in k6 and "DURATION=5s" in k6
    timeout = next(t for c, t in cmd.calls if K6_IMAGE in c)
    assert timeout == 25
    assert result["p95_ms"] == {"value": 30.1}
    assert result["cpu_max_pct"] == {"value": 20.0}


def test_measurer_https_mounts_lab_ca(tmp_path):
    cmd = FakeCmd(tmp_path)
    Measurer(tmp_path, guard=lambda e: None, cmd=cmd, sample_every=0.01).run(
        _scenario(measure={"path": "/healthz", "scheme": "https"}), 1, "fault"
    )
    k6 = next(c for c, _ in cmd.calls if K6_IMAGE in c)
    assert "SSL_CERT_FILE=/certs/ca.pem" in k6


def test_measurer_kind_network(tmp_path):
    cmd = FakeCmd(tmp_path, stats=None)
    result = Measurer(tmp_path, guard=lambda e: None, cmd=cmd, sample_every=0.01).run(
        _scenario(env="kind"), 1, "baseline"
    )
    k6 = next(c for c, _ in cmd.calls if K6_IMAGE in c)
    assert k6[k6.index("--network") + 1] == "kind"
    assert any("top" in c for c, _ in cmd.calls)
    assert result["cpu_avg_pct"] == {"status": "unavailable"}  # no metrics-server sample


@pytest.mark.parametrize(
    "code,summary", [("timeout", "summary_ok.json"), (1, "summary_ok.json"), (0, None)]
)
def test_measurer_failures_raise_and_record_nothing(tmp_path, code, summary):
    m = Measurer(
        tmp_path, guard=lambda e: None, cmd=FakeCmd(tmp_path, summary, code), sample_every=0.01
    )
    with pytest.raises(MeasureError):
        m.run(_scenario(), 1, "baseline")


def test_format_table_compares_only_measured_values():
    base = {"avg_ms": {"value": 10.0}, "error_rate": {"value": 0.0}, "p95_ms": {"value": 20.0}}
    now = {
        "avg_ms": {"value": 30.0},
        "error_rate": {"value": 1.0},
        "p95_ms": {"status": "not_applicable"},
        "cpu_max_pct": {"status": "unavailable"},
    }
    table = format_table(now, base)
    assert "| 평균 응답 시간 | 30.0 ms | ×3.0 |" in table
    assert "| p95 응답 시간 | 해당 없음 | — |" in table
    assert "| 오류율 | 100.0 % | — |" in table  # baseline 0 → no ratio
    assert "| CPU 최대 | 측정 불가 | — |" in table
    assert "| 처리량 | 측정하지 않음 | — |" in table
    assert "측정 생략(사유X)" in format_table(skipped(), skip_reason="사유X")


def _m(**values):
    return {k: ({"status": v} if isinstance(v, str) else {"value": v}) for k, v in values.items()}


BASE = _m(error_rate=0.0, avg_ms=10, p95_ms=20, cpu_max_pct=10, mem_max_mib=100)


@pytest.mark.parametrize(
    ("fault", "expected"),
    [
        (_m(error_rate=0.04, avg_ms=12, p95_ms=25, cpu_max_pct=25, mem_max_mib=120), []),
        (_m(error_rate=0.05), ["error_rate"]),
        (_m(avg_ms=15, p95_ms=21), ["avg_ms"]),
        (_m(avg_ms=6, p95_ms=13), ["avg_ms", "p95_ms"]),  # faster also counts (wrong cache)
        (
            _m(avg_ms="not_applicable", p95_ms="not_applicable"),
            ["avg_ms:not_applicable", "p95_ms:not_applicable"],
        ),
        (_m(cpu_max_pct=30), ["cpu_max_pct"]),
        (_m(mem_max_mib=130), ["mem_max_mib"]),
        (_m(cpu_max_pct="unavailable", mem_max_mib="unavailable"), []),
    ],
)
def test_fault_signals_sc005(fault, expected):
    assert fault_signals(BASE, fault) == expected
