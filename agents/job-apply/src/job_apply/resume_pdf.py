"""``resume.md`` → A4 ``resume.pdf`` with PyMuPDF Story (research R7)."""

from __future__ import annotations

from pathlib import Path

import markdown
import pymupdf

from job_apply.errors import UsageError

MARGIN_PT = 51  # 18 mm


def _font(font_file: Path | None) -> tuple[bytes, str]:
    if font_file is not None:
        return font_file.read_bytes(), f"resume{font_file.suffix.lower()}"
    return pymupdf.Font("cjk").buffer, "resume.ttf"


def build(resume_md: Path, out: Path, css: Path, font_file: Path | None) -> Path:
    text = resume_md.read_text(encoding="utf-8")
    if text.lstrip().startswith("---"):
        raise UsageError("resume.md에 frontmatter(---)는 쓸 수 없어요")
    html = markdown.markdown(text, extensions=["extra", "sane_lists"])
    font_bytes, font_name = _font(font_file)
    archive = pymupdf.Archive()
    archive.add(font_bytes, font_name)
    user_css = f'@font-face {{font-family: resume; src: url("{font_name}");}}\n' + css.read_text(
        encoding="utf-8"
    )
    story = pymupdf.Story(html=html, user_css=user_css, archive=archive)
    mediabox = pymupdf.paper_rect("a4")
    where = mediabox + (MARGIN_PT, MARGIN_PT, -MARGIN_PT, -MARGIN_PT)
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = pymupdf.DocumentWriter(str(out))
    more = True
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()
    return out
