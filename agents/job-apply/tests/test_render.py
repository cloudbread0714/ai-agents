import os
import subprocess
from pathlib import Path

import pymupdf
import pytest

from ja_support.fake_render import render as fake_render
from ja_support.samples import make_portfolio_pptx, make_resume_docx
from job_apply.errors import EnvNotReady, RenderError
from job_apply.render import SofficeRenderer, font_registry, render_previews, soffice_env


class FakeRun:
    def __init__(self, code=0, make_pdf=True, timeout=False):
        self.calls, self.code, self.make_pdf, self.timeout = [], code, make_pdf, timeout

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        if self.timeout:
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        if self.make_pdf:
            out = Path(cmd[cmd.index("--outdir") + 1]) / (Path(cmd[-1]).stem + ".pdf")
            out.write_bytes(b"%PDF-1.4")
        return subprocess.CompletedProcess(cmd, self.code, "", "boom")


def test_soffice_command_profile_and_timeout(tmp_path):
    run = FakeRun()
    r = SofficeRenderer(tmp_path / "lo", timeout_s=7, run=run, which=lambda n: "/opt/bin/soffice")
    pdf = r.to_pdf(tmp_path / "deck.pptx", tmp_path / "out")
    cmd, kw = run.calls[0]
    assert cmd[:2] == ["/opt/bin/soffice", "--headless"]
    assert cmd[2] == f"-env:UserInstallation={(tmp_path / 'lo').resolve().as_uri()}"
    assert cmd[3:7] == ["--convert-to", "pdf", "--outdir", str(tmp_path / "out")]
    assert kw["timeout"] == 7 and pdf == tmp_path / "out" / "deck.pdf"


def test_font_substitutes_go_into_the_profile(tmp_path):
    subs = {"맑은 고딕": "Apple SD Gothic Neo", "A&B": "C"}
    r = SofficeRenderer(tmp_path / "lo", font_substitutes=subs, run=FakeRun(), which=lambda n: "x")
    r.to_pdf(tmp_path / "resume.docx", tmp_path / "out")
    xcu = (tmp_path / "lo" / "user" / "registrymodifications.xcu").read_text()
    assert xcu == font_registry(subs)
    assert "<value>맑은 고딕</value>" in xcu and "<value>A&amp;B</value>" in xcu
    assert "<value>true</value></prop></item>" in xcu
    assert "<value>false</value></prop></item>" in font_registry({})


def test_macos_uses_osx_backend_for_system_fonts(monkeypatch):
    monkeypatch.delenv("SAL_USE_VCLPLUGIN", raising=False)
    assert soffice_env("darwin")["SAL_USE_VCLPLUGIN"] == "osx"
    assert "SAL_USE_VCLPLUGIN" not in soffice_env("linux")
    monkeypatch.setenv("SAL_USE_VCLPLUGIN", "svp")
    assert soffice_env("darwin")["SAL_USE_VCLPLUGIN"] == "svp"


def test_missing_soffice_is_env_not_ready(tmp_path):
    with pytest.raises(EnvNotReady):
        SofficeRenderer(tmp_path, run=FakeRun(), which=lambda n: None).to_pdf(
            tmp_path / "a.pptx", tmp_path
        )


@pytest.mark.parametrize("run", [FakeRun(code=1, make_pdf=False), FakeRun(timeout=True)])
def test_failures_raise_render_error(tmp_path, run):
    with pytest.raises(RenderError):
        SofficeRenderer(tmp_path, run=run, which=lambda n: "soffice").to_pdf(
            tmp_path / "a.pptx", tmp_path
        )


def test_previews_replace_old_ones(tmp_path):
    pdf = fake_render(make_portfolio_pptx(tmp_path / "deck.pptx"), tmp_path)
    out = tmp_path / "preview"
    out.mkdir()
    (out / "slide-09.png").write_bytes(b"old")
    written = render_previews(pdf, [4, 2], out, 50)
    assert [p.name for p in written] == ["slide-02.png", "slide-04.png"]
    assert sorted(p.name for p in out.iterdir()) == ["slide-02.png", "slide-04.png"]
    assert pymupdf.open(written[0]).page_count == 1


render = pytest.mark.skipif(
    os.environ.get("JOB_RENDER") != "1", reason="needs LibreOffice; JOB_RENDER=1"
)


@render
@pytest.mark.render
def test_real_libreoffice_converts_sample(tmp_path):
    deck = make_portfolio_pptx(tmp_path / "deck.pptx")
    pdf = SofficeRenderer(tmp_path / "lo").to_pdf(deck, tmp_path / "out")
    with pymupdf.open(pdf) as doc:
        # macOS's osx backend writes word gaps as positioning, not space characters
        assert doc.page_count == 5 and "핵심역량" in "".join(doc[1].get_text().split())


@render
@pytest.mark.render
def test_real_libreoffice_overflow_detected_and_base_overlap_ignored(tmp_path):
    from ja_support import session
    from job_apply import layout_check, pptx_apply
    from job_apply.models import parse_plan

    deck = make_portfolio_pptx(tmp_path / "base.pptx")
    renderer = SofficeRenderer(tmp_path / "lo")
    base_pdf = renderer.to_pdf(deck, tmp_path / "base")
    long_text = "응답 시간 개선 경험을 길게 설명하는 문장입니다 " * 8
    plan = parse_plan(
        session.plan(
            edits=[
                {
                    "slide": 2,
                    "shape_id": 4,
                    "paragraph": 0,
                    "text": long_text,
                    "source": "portfolio.json:s2/sh4/p0",
                    "reason": "넘침 확인용 긴 문장",
                }
            ]
        ),
        5,
    )
    out = tmp_path / "result.pptx"
    out.write_bytes(pptx_apply.apply(deck, plan))
    pdf = renderer.to_pdf(out, tmp_path / "result")
    base_issues = layout_check.find_issues(deck, base_pdf, 4)
    issues = layout_check.new_issues(
        layout_check.find_issues(out, pdf, 4), base_issues, plan.portfolio.slide_order
    )
    assert any(i.kind == "overflow" and i.slide == 2 and i.shape_id == 4 for i in issues)
    assert not any(i.slide == 4 for i in issues)


@render
@pytest.mark.render
def test_real_libreoffice_converts_resume_docx(tmp_path):
    from ja_support.samples import RESUME_LINES

    docx = make_resume_docx(tmp_path / "resume.docx")
    pdf = SofficeRenderer(tmp_path / "lo").to_pdf(docx, tmp_path / "out")
    with pymupdf.open(pdf) as doc:
        pages, text = doc.page_count, "".join(doc[0].get_text().split())
    assert pages == 1 and "".join(RESUME_LINES[5].split()) in text
