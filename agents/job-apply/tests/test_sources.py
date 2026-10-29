import os

import pytest

from job_apply import sources
from job_apply.config import Paths
from job_apply.errors import SourceChangedError, SourceError


def test_missing_and_unreadable_originals(job_root):
    paths = Paths(job_root)
    paths.portfolio.unlink()
    with pytest.raises(SourceError, match="portfolio.pptx"):
        sources.check(paths)
    paths.portfolio.write_bytes(b"not a pptx")
    with pytest.raises(SourceError, match="portfolio.pptx"):
        sources.check(paths)
    assert SourceError.exit_code == 5


def test_guard_detects_change(job_root):
    paths = Paths(job_root)
    with sources.guard(paths):
        pass
    with pytest.raises(SourceChangedError) as excinfo, sources.guard(paths):
        paths.resume.write_bytes(paths.resume.read_bytes() + b"\n%")
    assert excinfo.value.exit_code == 8 and excinfo.value.names == ["resume.pdf"]


def test_reading_leaves_originals_untouched(job_root, tmp_path):
    paths = Paths(job_root)
    before = {p: (p.read_bytes(), os.stat(p).st_mtime_ns) for p in (paths.resume, paths.portfolio)}
    sources.check(paths)
    sources.current(paths)
    sources.copy_to_base(paths, tmp_path / "base")
    sources.extract_resume_text(paths.resume, tmp_path / "resume.txt")
    assert before == {p: (p.read_bytes(), os.stat(p).st_mtime_ns) for p in before}


def test_resume_text_lines_are_numbered_by_file_line(job_root, tmp_path):
    out = tmp_path / "resume.txt"
    lines = sources.extract_resume_text(Paths(job_root).resume, out)
    text = out.read_text().splitlines()
    assert text == lines
    assert text[0] == "홍길동" and "PostgreSQL 쿼리 튜닝으로 응답 시간 30% 개선" in text[5]
