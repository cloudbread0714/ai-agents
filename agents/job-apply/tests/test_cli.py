import logging

import pytest

from job_apply.cli import main
from job_apply.errors import JobError


def test_help_and_bad_usage(job, capsys):

    assert main(["--help"], root=job.root) == 0
    assert main(["init"], root=job.root) == 2


def test_result_line_and_exit_code_mapping(job):
    code, res, out = job("apply", "nowhere")
    assert code == 2 and res["exit"] == 2 and "지원 폴더를 찾을 수 없어요" in out
    code, res, _ = job("status")
    assert code == 0 and res == {"folders": []}


@pytest.mark.parametrize("exit_code", [2, 4, 5, 6, 7, 8, 9])
def test_job_errors_map_to_exit_codes(job, monkeypatch, exit_code):
    from job_apply import cli

    class Boom(JobError):
        pass

    Boom.exit_code = exit_code

    def fail(ctx, args):
        raise Boom("boom")

    monkeypatch.setitem(cli.COMMANDS, "status", fail)
    code, res, _ = job("status")
    assert code == exit_code and res == {"error": "boom", "exit": exit_code}


def test_unexpected_error_is_exit_1(job, monkeypatch):
    from job_apply import cli

    monkeypatch.setitem(cli.COMMANDS, "status", lambda ctx, args: 1 / 0)
    code, res, _ = job("status")
    assert code == 1 and "ZeroDivisionError" in res["error"]


def test_logs_go_to_job_log(job, monkeypatch):
    from job_apply import cli

    monkeypatch.setitem(cli.COMMANDS, "status", lambda ctx, args: 1 / 0)
    job("status")
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert "unexpected_error" in (job.root / ".job-state" / "logs" / "job.log").read_text()


def test_original_changed_mid_command_is_exit_8(job, monkeypatch):
    from job_apply import cli

    def touch(ctx, args):
        ctx.paths.resume.write_bytes(ctx.paths.resume.read_bytes() + b"%")
        return 0, {}

    monkeypatch.setitem(cli.COMMANDS, "status", touch)
    code, res, out = job("status")
    assert code == 8 and "원본이 처리 중에 바뀜" in out
