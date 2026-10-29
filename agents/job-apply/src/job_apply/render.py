"""PPTX → PDF with LibreOffice, PDF → PNG previews (research R4, R5).

The renderer is injected so the default tests need no LibreOffice.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

import pymupdf

from job_apply.errors import EnvNotReady, RenderError
from shared.logging import get_logger

log = get_logger(__name__)

Run = Callable[..., subprocess.CompletedProcess]


def soffice_env(platform: str = sys.platform) -> dict[str, str]:
    """On macOS, --headless picks the ``svp`` backend, which sees only LibreOffice's bundled
    fonts; every Hangul glyph then drops out. The ``osx`` backend stays headless and uses the
    system and user fonts."""
    env = dict(os.environ)
    if platform == "darwin":
        env.setdefault("SAL_USE_VCLPLUGIN", "osx")
    return env


class Renderer(Protocol):
    def to_pdf(self, pptx: Path, out_dir: Path) -> Path: ...


class SofficeRenderer:
    def __init__(
        self,
        profile: Path,
        *,
        timeout_s: float = 120,
        run: Run = subprocess.run,
        which: Callable[[str], str | None] = shutil.which,
    ):
        self.profile = profile
        self.timeout_s = timeout_s
        self.run = run
        self.which = which

    def binary(self) -> str:
        found = self.which("soffice")
        if not found:
            raise EnvNotReady(
                "LibreOffice(soffice)가 없어요: brew install --cask libreoffice 로 설치하세요"
            )
        return found

    def command(self, pptx: Path, out_dir: Path) -> list[str]:
        return [
            self.binary(),
            "--headless",
            f"-env:UserInstallation={self.profile.resolve().as_uri()}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(pptx),
        ]

    def to_pdf(self, pptx: Path, out_dir: Path) -> Path:
        cmd = self.command(pptx, out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        self.profile.mkdir(parents=True, exist_ok=True)
        try:
            proc = self.run(
                cmd, capture_output=True, text=True, timeout=self.timeout_s, env=soffice_env()
            )
        except subprocess.TimeoutExpired:
            log.error("render_timeout", extra={"fields": {"file": pptx.name}})
            raise RenderError(f"렌더링이 {self.timeout_s:.0f}초 안에 끝나지 않았어요") from None
        out = out_dir / f"{pptx.stem}.pdf"
        if proc.returncode != 0 or not out.is_file():
            log.error(
                "render_failed",
                extra={
                    "fields": {
                        "file": pptx.name,
                        "code": proc.returncode,
                        "stderr": proc.stderr[-300:],
                    }
                },
            )
            raise RenderError(f"렌더링 실패(종료 코드 {proc.returncode})")
        return out


def render_previews(pdf: Path, pages: Sequence[int], out_dir: Path, dpi: int) -> list[Path]:
    """PNG of each 1-based page in ``pages`` as ``slide-NN.png``. Old previews are removed."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("slide-*.png"):
        old.unlink()
    written = []
    with pymupdf.open(pdf) as doc:
        for n in sorted(set(pages)):
            target = out_dir / f"slide-{n:02d}.png"
            doc.load_page(n - 1).get_pixmap(dpi=dpi).save(target)
            written.append(target)
    return written


def to_pdf_at(renderer: Renderer, pptx: Path, target: Path, work: Path) -> Path:
    """Render into ``work`` and move the PDF to ``target``."""
    pdf = renderer.to_pdf(pptx, work)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(pdf), target)
    return target
