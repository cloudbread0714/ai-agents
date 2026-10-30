import subprocess

import yaml

from ja_support.samples import make_portfolio_pptx, make_resume_docx
from job_apply.doctor import docx_fonts, pptx_fonts

API = "https://slack.com/api/"


class FakeRun:
    def __init__(self, ignored=None, fonts="Calibri\nNanum Gothic,나눔고딕\nPretendard\n"):
        self.ignored, self.fonts, self.calls = ignored, fonts, []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if cmd[:2] == ["git", "check-ignore"]:
            paths = cmd[2:] if self.ignored is None else [p for p in cmd[2:] if p in self.ignored]
            return subprocess.CompletedProcess(cmd, 0 if paths else 1, "\n".join(paths), "")
        if cmd[0] == "fc-list":
            return subprocess.CompletedProcess(cmd, 0, self.fonts, "")
        raise AssertionError(cmd)


def _doctor(job, run, which=lambda n: f"/usr/bin/{n}"):
    job.run, job.which = run, which
    return job("doctor")


def _slack_ok(httpx_mock):
    httpx_mock.add_response(url=API + "auth.test", json={"ok": True, "user_id": "U0BOT"})
    httpx_mock.add_response(
        url=f"{API}conversations.history?channel=C0JOB&limit=1", json={"ok": True, "messages": []}
    )


def test_all_good(job, httpx_mock):
    _slack_ok(httpx_mock)
    code, res, out = _doctor(job, FakeRun())
    assert code == 0 and res["ok"] and res["slack_ready"], out
    assert res["missing"] == [] and res["warnings"] == []
    assert "Authorization" not in out and "xoxb" not in out


def test_missing_soffice_original_and_gitignore(job, httpx_mock):
    _slack_ok(httpx_mock)
    (job.root / "private" / "resume.docx").unlink()
    code, res, out = _doctor(job, FakeRun(ignored=[]), which=lambda n: None)
    assert code == 5 and set(res["missing"]) == {"sources", "soffice", "gitignore"}


def test_missing_fonts_and_no_fc_list_are_warnings(job, httpx_mock, tmp_path):
    _slack_ok(httpx_mock)
    code, res, _ = _doctor(job, FakeRun(fonts="Something Else\n"))
    assert code == 0 and any("Calibri" in w for w in res["warnings"])
    assert any(w.startswith("이력서 글꼴") and "Pretendard" in w for w in res["warnings"])
    _slack_ok(httpx_mock)
    code, res, _ = _doctor(job, FakeRun(), which=lambda n: None if n == "fc-list" else n)
    assert code == 0 and any("fc-list" in w for w in res["warnings"])


def test_slack_not_ready_is_only_a_warning(job, httpx_mock):
    job.environ = {}
    code, res, _ = _doctor(job, FakeRun())
    assert code == 0 and res["ok"] and not res["slack_ready"]
    job.environ = {"SLACK_BOT_TOKEN": "xoxb-test-secret"}
    httpx_mock.add_response(url=API + "auth.test", json={"ok": False, "error": "invalid_auth"})
    code, res, _ = _doctor(job, FakeRun())
    assert not res["slack_ready"] and any("invalid_auth" in w for w in res["warnings"])


def test_pptx_fonts_skip_theme_placeholders(tmp_path):
    fonts = pptx_fonts(make_portfolio_pptx(tmp_path / "deck.pptx"))
    assert "Calibri" in fonts and not any(f.startswith("+") for f in fonts)


def test_resume_fonts_and_substitutes(job, httpx_mock, tmp_path):
    assert docx_fonts(make_resume_docx(tmp_path / "r.docx")) == {"Pretendard"}
    cfg_path = job.root / "config" / "job.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["render"]["font_substitutes"] = {"Pretendard": "Nanum Gothic"}
    cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True))
    _slack_ok(httpx_mock)
    code, res, out = _doctor(job, FakeRun(fonts="Calibri\nNanum Gothic\n"))
    assert code == 0 and res["warnings"] == [] and "이력서 글꼴이 모두 설치돼 있어요" in out
