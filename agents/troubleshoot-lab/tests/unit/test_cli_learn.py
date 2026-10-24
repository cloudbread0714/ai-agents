import io
import json

import pytest

from tl_support import hint_sentinel, tag_sentinel
from troubleshoot_lab.cli import _command, main
from troubleshoot_lab.diag import DiagResult
from troubleshoot_lab.sync import SyncResult


def run_cli(argv, lab_root, learner, **kw):
    out = io.StringIO()
    code = main(
        argv, lab_root=lab_root, environ={}, out=out, learner_factory=lambda r, e: learner, **kw
    )
    return code, out.getvalue().rstrip("\n").splitlines()


def _result(lines):
    assert lines[-1].startswith("LAB_RESULT ")
    return json.loads(lines[-1].removeprefix("LAB_RESULT "))


@pytest.mark.parametrize(
    "argv,code,outcome",
    [
        (["start", "nope"], 2, "unknown"),
        (["start", "d-easy"], 4, "locked"),
        (["measure"], 4, "none"),
        (["inject"], 4, "none"),
        (["hint"], 4, "none"),
        (["check"], 4, "none"),
        (["giveup"], 4, "none"),
        (["report"], 4, "none"),
        (["start", "m-one"], 0, "ok"),
        (["list"], 0, "ok"),
    ],
)
def test_exit_codes_and_result_line(lab_root, learner, argv, code, outcome):
    got, lines = run_cli(argv, lab_root, learner)
    assert got == code
    result = _result(lines)
    assert result["outcome"] == outcome and result["command"] == argv[0]


def test_scenario_result_line_has_attempt_and_stage(lab_root, learner):
    for argv in (["start", "m-one"], ["check"], ["check", "tok"]):
        run_cli(argv, lab_root, learner)
    _, lines = run_cli(["start", "w-easy"], lab_root, learner)
    assert _result(lines) | {} == {
        "command": "start", "kind": "scenario", "id": "w-easy", "outcome": "ok",
        "sync_suggested": False, "attempt": 1, "stage": "started",
    }
    code, lines = run_cli(["measure", "--skip", "도구 없음"], lab_root, learner)
    assert code == 0 and _result(lines)["outcome"] == "skipped"


def test_exec_passes_service_command_and_env(lab_root, learner):
    calls = []

    class FakeDiag:
        def exec(self, service, command, env_name):
            calls.append((service, command, env_name))
            return DiagResult("ok", 0, "LISTEN")

        def shell(self, service, env_name):
            return f"docker run -it {service}"

    learner.diagnoser = FakeDiag()
    code, lines = run_cli(["exec", "api", "--", "ss", "-lntp"], lab_root, learner)
    assert code == 0 and lines[0] == "LISTEN"
    assert calls == [("api", "ss -lntp", "compose")]
    run_cli(["exec", "--env", "kind", "nginx", "--", "ss", "-ant", "|", "wc", "-l"], lab_root, learner)
    assert calls[-1] == ("nginx", "ss -ant | wc -l", "kind")
    _, lines = run_cli(["shell", "redis"], lab_root, learner)
    assert "docker run -it redis" in "\n".join(lines)


def test_command_joining():
    assert _command(["--", "ss", "-lntp"]) == "ss -lntp"
    assert _command(["ss -ant | wc -l"]) == "ss -ant | wc -l"
    assert _command([]) == "true"


def test_not_ready_and_refused_codes(lab_root, learner):
    from troubleshoot_lab.guard import EnvNotReady, SandboxError

    def raise_(exc):
        def g(env):
            raise exc

        return g

    learner.guard = raise_(EnvNotReady("x"))
    assert run_cli(["start", "m-one"], lab_root, learner)[0] == 5
    learner.guard = raise_(SandboxError("y"))
    assert run_cli(["start", "m-one"], lab_root, learner)[0] == 3


def test_list_never_prints_hidden_text(lab_root, learner):
    _, lines = run_cli(["list"], lab_root, learner)
    text = "\n".join(lines)
    assert tag_sentinel("d-easy") not in text and hint_sentinel("d-easy", 1) not in text


def test_validate_prints_plan_minutes(lab_root, learner):
    code, lines = run_cli(["validate"], lab_root, learner)
    assert code == 0 and "오류 0" in lines[0]
    assert any("1일 차 (60분)" in line for line in lines)
    (lab_root / "scenarios" / "linux" / "d-easy" / "solution.md").write_text("")
    code, lines = run_cli(["validate"], lab_root, learner)
    assert code == 2 and "solution.md is empty" in "\n".join(lines)


def test_env_prints_exports(lab_root, learner):
    code, lines = run_cli(["env"], lab_root, learner)
    assert code == 0
    assert lines[0] == f"export KUBECONFIG={lab_root / 'environment' / '.kube' / 'config'}"
    assert any(line.startswith("export COMPOSE_FILE=") for line in lines)


def test_sync_passes_through(lab_root, learner):
    code, lines = run_cli(
        ["sync"], lab_root, learner,
        sync_fn=lambda root: SyncResult(4, "브랜치가 main이 아니에요", "wrong_branch"),
    )
    assert code == 4 and _result(lines)["outcome"] == "wrong_branch"


def test_bad_usage_is_exit_2(lab_root, learner):
    assert run_cli(["bogus"], lab_root, learner)[0] == 2
