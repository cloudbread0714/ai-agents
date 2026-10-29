"""US5: new versions of the originals, and originals changing mid-command."""

import json

from ja_support import session
from ja_support.fake_render import FakeRenderer
from ja_support.flow import ready, start
from ja_support.samples import RESUME_LINES, make_portfolio_pptx, make_posting_html, make_resume_pdf
from job_apply import sources


def _files(folder):
    return {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def test_new_original_is_used_by_the_next_folder_only(job, httpx_mock):
    a = ready(job, httpx_mock)
    assert job("complete", str(a))[0] == 0
    before = _files(a)
    make_resume_pdf(job.root / "private" / "resume.pdf", [*RESUME_LINES, "Redis 캐시 도입"])
    url_b = "https://jobs.example.com/postings/456"
    httpx_mock.add_response(url=url_b, text=make_posting_html("jsonld"))
    _code, res, _ = job("fetch", url_b)
    _code, init, _ = job("init", res["id"], "--company", "샘플랩스", "--role", "백엔드 개발자")
    b = job.root.parents[1] / init["folder"]
    meta_a = json.loads((a / "meta.json").read_text())["sources"]
    meta_b = json.loads((b / "meta.json").read_text())["sources"]
    assert meta_a["resume"]["sha256"] != meta_b["resume"]["sha256"]
    assert meta_a["portfolio"]["sha256"] == meta_b["portfolio"]["sha256"]
    assert "Redis 캐시 도입" in (b / "base" / "resume.txt").read_text()
    assert _files(a) == before
    session.write(b)
    assert job("resume-pdf", str(b))[0] == 0 and job("apply", str(b))[0] == 0
    assert job("complete", str(b))[0] == 0
    assert meta_b["resume"]["sha256"][:12] in (b / "changes.md").read_text()
    assert meta_a["resume"]["sha256"][:12] in (a / "changes.md").read_text()


def test_replacing_original_between_commands_does_not_touch_the_folder(job, httpx_mock):
    _id, folder = start(job, httpx_mock)
    sources_before = json.loads((folder / "meta.json").read_text())["sources"]
    deck = job.root / "private" / "portfolio.pptx"
    make_portfolio_pptx(deck)  # a new file (new bytes) between init and apply
    session.write(folder)
    assert job("resume-pdf", str(folder))[0] == 0
    assert job("apply", str(folder))[0] == 0
    assert job.renderer.calls[-1] == folder / "portfolio.pptx"
    assert json.loads((folder / "meta.json").read_text())["sources"] == sources_before
    assert (
        sources.sha256(folder / "base" / "portfolio.pptx") == sources_before["portfolio"]["sha256"]
    )
    assert job("complete", str(folder))[0] == 0


class ChangingRenderer(FakeRenderer):
    def __init__(self, resume):
        super().__init__()
        self.resume = resume

    def to_pdf(self, pptx, out_dir):
        self.resume.write_bytes(self.resume.read_bytes() + b"%changed")
        return super().to_pdf(pptx, out_dir)


def test_original_changing_while_a_command_runs_fails_the_folder(job, httpx_mock):
    job.renderer = ChangingRenderer(job.root / "private" / "resume.pdf")
    httpx_mock.add_response(url="https://jobs.example.com/x", text=make_posting_html("jsonld"))
    _code, res, _ = job("fetch", "https://jobs.example.com/x")
    code, out_res, out = job("init", res["id"], "--company", "가상테크", "--role", "백엔드")
    assert code == 8 and "원본이 처리 중에 바뀜" in out
    [folder] = (job.root / "applications").iterdir()
    meta = json.loads((folder / "meta.json").read_text())
    assert meta["status"] == "failed" and meta["error"]["reason"] == "원본이 처리 중에 바뀜"
