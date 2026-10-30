"""PPTX/DOCX → PDF with LibreOffice, PDF → PNG previews (research R4, R5, R7).

The renderer is injected so the default tests need no LibreOffice.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol
from xml.sax.saxutils import escape, quoteattr

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
    def to_pdf(self, document: Path, out_dir: Path) -> Path: ...


_REGISTRY = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" \
xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Common/Font/Substitution">\
<prop oor:name="Replacement" oor:op="fuse"><value>{on}</value></prop></item>
{pairs}</oor:items>
"""
_PAIR = (
    '<item oor:path="/org.openoffice.Office.Common/Font/Substitution/FontPairs">'
    '<node oor:name={name} oor:op="replace">'
    # Always=true: with false, LibreOffice treats a font its own fallback table knows
    # (e.g. 맑은 고딕) as present and never substitutes.
    '<prop oor:name="Always" oor:op="fuse"><value>true</value></prop>'
    '<prop oor:name="OnScreenOnly" oor:op="fuse"><value>false</value></prop>'
    '<prop oor:name="ReplaceFont" oor:op="fuse"><value>{old}</value></prop>'
    '<prop oor:name="SubstituteFont" oor:op="fuse"><value>{new}</value></prop>'
    "</node></item>\n"
)


def font_registry(substitutes: Mapping[str, str]) -> str:
    """LibreOffice user settings with a font replacement table (Tools ▸ Options ▸ Fonts)."""
    pairs = "".join(
        _PAIR.format(name=quoteattr(f"_{i}"), old=escape(old), new=escape(new))
        for i, (old, new) in enumerate(substitutes.items())
    )
    return _REGISTRY.format(on="true" if substitutes else "false", pairs=pairs)


class SofficeRenderer:
    def __init__(
        self,
        profile: Path,
        *,
        timeout_s: float = 120,
        font_substitutes: Mapping[str, str] | None = None,
        run: Run = subprocess.run,
        which: Callable[[str], str | None] = shutil.which,
    ):
        self.profile = profile
        self.timeout_s = timeout_s
        self.font_substitutes = dict(font_substitutes or {})
        self.run = run
        self.which = which

    def binary(self) -> str:
        found = self.which("soffice")
        if not found:
            raise EnvNotReady(
                "LibreOffice(soffice)가 없어요: brew install --cask libreoffice 로 설치하세요"
            )
        return found

    def command(self, document: Path, out_dir: Path) -> list[str]:
        return [
            self.binary(),
            "--headless",
            f"-env:UserInstallation={self.profile.resolve().as_uri()}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(document),
        ]

    def to_pdf(self, document: Path, out_dir: Path) -> Path:
        cmd = self.command(document, out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        # The profile is ours alone (.job-state/lo-profile), so its settings file is rewritten
        # before every run.
        (self.profile / "user").mkdir(parents=True, exist_ok=True)
        (self.profile / "user" / "registrymodifications.xcu").write_text(
            font_registry(self.font_substitutes), encoding="utf-8"
        )
        try:
            proc = self.run(
                cmd, capture_output=True, text=True, timeout=self.timeout_s, env=soffice_env()
            )
        except subprocess.TimeoutExpired:
            log.error("render_timeout", extra={"fields": {"file": document.name}})
            raise RenderError(f"렌더링이 {self.timeout_s:.0f}초 안에 끝나지 않았어요") from None
        out = out_dir / f"{document.stem}.pdf"
        if proc.returncode != 0 or not out.is_file():
            log.error(
                "render_failed",
                extra={
                    "fields": {
                        "file": document.name,
                        "code": proc.returncode,
                        "stderr": proc.stderr[-300:],
                    }
                },
            )
            raise RenderError(f"렌더링 실패(종료 코드 {proc.returncode})")
        return out


def page_count(pdf: Path) -> int:
    with pymupdf.open(pdf) as doc:
        return doc.page_count


def render_previews(
    pdf: Path, pages: Sequence[int], out_dir: Path, dpi: int, prefix: str = "slide"
) -> list[Path]:
    """PNG of each 1-based page in ``pages`` as ``<prefix>-NN.png``. Old previews with the
    same prefix are removed."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob(f"{prefix}-*.png"):
        old.unlink()
    written = []
    with pymupdf.open(pdf) as doc:
        for n in sorted(set(pages)):
            target = out_dir / f"{prefix}-{n:02d}.png"
            doc.load_page(n - 1).get_pixmap(dpi=dpi).save(target)
            written.append(target)
    return written


def to_pdf_at(renderer: Renderer, document: Path, target: Path, work: Path) -> Path:
    """Render into ``work`` and move the PDF to ``target``."""
    pdf = renderer.to_pdf(document, work)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(pdf), target)
    return target
