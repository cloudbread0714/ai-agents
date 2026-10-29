from __future__ import annotations

import io
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from ja_support.fake_render import FakeRenderer
from ja_support.samples import make_portfolio_pptx, make_resume_pdf

AGENT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 27, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
TOKEN = "xoxb-test-secret"
ENV = {"SLACK_BOT_TOKEN": TOKEN}


@pytest.fixture
def job_root(tmp_path: Path) -> Path:
    """A copy of the agent layout at <tmp>/repo/agents/job-apply with sample originals."""
    root = tmp_path / "repo" / "agents" / "job-apply"
    (root / "config").mkdir(parents=True)
    shutil.copytree(AGENT / "templates", root / "templates")
    cfg = yaml.safe_load((AGENT / "config" / "job.yaml").read_text(encoding="utf-8"))
    cfg["slack"]["channel_id"] = "C0JOB"
    cfg["resume"]["font_files"] = []  # deterministic: built-in CJK font
    (root / "config" / "job.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True))
    for d in ("applications", ".job-state"):
        (root / d).mkdir()
    make_resume_pdf(root / "private" / "resume.pdf")
    make_portfolio_pptx(root / "private" / "portfolio.pptx")
    return root


@pytest.fixture
def fake_renderer() -> FakeRenderer:
    return FakeRenderer()


class JobRunner:
    def __init__(self, root: Path, renderer: FakeRenderer):
        self.root, self.renderer = root, renderer
        self.environ: dict[str, str] = dict(ENV)
        self.now = NOW
        self.run = None
        self.which = None

    def __call__(self, *argv: str):
        from job_apply.cli import main

        out = io.StringIO()
        kw = {}
        if self.run is not None:
            kw["run"] = self.run
        if self.which is not None:
            kw["which"] = self.which
        code = main(
            list(argv),
            root=self.root,
            environ=self.environ,
            renderer=self.renderer,
            now=self.now,
            out=out,
            base_delay=0,
            **kw,
        )
        text = out.getvalue()
        last = text.strip().splitlines()[-1]
        assert last.startswith("JOB_RESULT "), text
        return code, json.loads(last.removeprefix("JOB_RESULT ")), text


@pytest.fixture
def job(job_root, fake_renderer) -> JobRunner:
    return JobRunner(job_root, fake_renderer)
