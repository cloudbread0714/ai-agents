import pymupdf
import pytest

from ja_support.session import RESUME
from job_apply.config import AGENT_ROOT
from job_apply.errors import UsageError
from job_apply.resume_pdf import build

CSS = AGENT_ROOT / "templates" / "resume.css"


def test_a4_with_builtin_cjk_font(tmp_path):
    md = tmp_path / "resume.md"
    md.write_text(RESUME.format(extra=""))
    pdf = build(md, tmp_path / "resume.pdf", CSS, None)
    with pymupdf.open(pdf) as doc:
        page = doc[0]
        assert round(page.rect.width) == 595 and round(page.rect.height) == 842
        text = page.get_text()
    assert "홍길동" in text and "PostgreSQL 쿼리 튜닝으로 응답 시간 30% 개선" in text


def test_frontmatter_is_rejected(tmp_path):
    md = tmp_path / "resume.md"
    md.write_text("---\ntitle: x\n---\n# 홍길동\n")
    with pytest.raises(UsageError):
        build(md, tmp_path / "resume.pdf", CSS, None)


def test_long_resume_spans_pages(tmp_path):
    md = tmp_path / "resume.md"
    md.write_text("# 홍길동\n\n" + "\n".join(f"- 항목 {i} 설명 문장" for i in range(200)))
    with pymupdf.open(build(md, tmp_path / "resume.pdf", CSS, None)) as doc:
        assert doc.page_count >= 2
