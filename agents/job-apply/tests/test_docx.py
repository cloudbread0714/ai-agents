import io
import re
import zipfile

import pytest

from ja_support import session
from ja_support.samples import RESUME_LINES, make_resume_docx
from job_apply import docx_doc, docx_guard
from job_apply.errors import DesignViolation, PlanError
from job_apply.models import parse_plan


@pytest.fixture
def resume(tmp_path):
    return make_resume_docx(tmp_path / "resume.docx")


def _apply(resume, edits=None, row_order=None):
    data = session.plan(resume_edits=edits or [], row_order=row_order or [])
    return docx_doc.apply(resume, parse_plan(data, 5))


def _texts(blob: bytes) -> list[str]:
    return [p["text"] for p in docx_doc.dump(docx_doc.read_document(blob))["paragraphs"]]


def _edit(paragraph, **change):
    return {"paragraph": paragraph, **change, "source": "resume.txt:L1", "reason": "테스트용 수정"}


def test_dump_numbers_paragraphs_and_lines(resume, tmp_path):
    data = docx_doc.dump_file(resume, tmp_path / "r.json", tmp_path / "r.txt")
    assert data["paragraph_count"] == 9 and data["tables"] == [{"table": 1, "rows": 4}]
    row = data["paragraphs"][5]
    assert (row["table"], row["row"], row["cell"], row["line"]) == (1, 2, 0, 6)
    assert row["text"] == RESUME_LINES[5]
    assert (tmp_path / "r.txt").read_text().splitlines() == RESUME_LINES


def test_text_keeps_the_first_run_format(resume):
    out = _apply(resume, [_edit(3, text="새 회사 (2021-2024)"), _edit(8, text="첫 줄\n둘째 줄")])
    assert _texts(out)[3] == "새 회사 (2021-2024)" and _texts(out)[8] == "첫 줄\n둘째 줄"
    doc = docx_doc.read_document(out)
    first_row = list(docx_doc.walk(doc))[3][0]
    assert first_row.find(f".//{docx_doc.W}b") is not None  # bold run kept
    docx_guard.check(resume, out)


def test_runs_must_match_run_count(resume):
    with pytest.raises(PlanError, match="run 개수"):
        _apply(resume, [_edit(0, runs=["a", "b"])])


def test_insert_delete_and_row_order(resume):
    out = _apply(
        resume,
        [
            _edit(4, op={"kind": "insert_after", "text": "추가 문단"}),
            _edit(1, op={"kind": "delete"}),
        ],
        [{"table": 1, "order": [0, 3, 1, 2], "reason": "테스트용 순서"}],
    )
    texts = _texts(out)
    assert RESUME_LINES[1] not in texts
    assert texts[2:7] == [
        RESUME_LINES[3],
        RESUME_LINES[6],
        RESUME_LINES[4],
        "추가 문단",
        RESUME_LINES[5],
    ]
    docx_guard.check(resume, out)


@pytest.mark.parametrize(
    ("edits", "row_order", "match"),
    [
        ([_edit(99, text="x")], None, "문단 99"),
        ([_edit(3, op={"kind": "delete"})], None, "마지막 문단"),
        (None, [{"table": 2, "order": [0], "reason": "없는 표 순서"}], "표 2"),
        (None, [{"table": 1, "order": [0, 1, 1, 2], "reason": "중복 행 순서"}], "순열"),
    ],
)
def test_bad_targets_are_plan_errors(resume, edits, row_order, match):
    with pytest.raises(PlanError, match=match):
        _apply(resume, edits, row_order)


def _mutate(blob: bytes, name: str, fn) -> bytes:
    src, out = zipfile.ZipFile(io.BytesIO(blob)), io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            dst.writestr(item, fn(data) if item.filename == name else data)
    return out.getvalue()


def _sub(pattern, repl):
    return lambda data: re.sub(pattern.encode(), repl.encode(), data, count=1)


@pytest.mark.parametrize(
    ("part", "mutation"),
    [
        ("word/document.xml", _sub(r'<w:tcW w:w="9000"', '<w:tcW w:w="100"')),  # cell width
        ("word/document.xml", _sub(r'w:val="single"', 'w:val="double"')),  # border
        ("word/document.xml", _sub(r"<w:r><w:t ", "<w:r><w:rPr><w:i/></w:rPr><w:t ")),  # format
        ("word/document.xml", _sub(r"</w:body>", "<w:p/><w:sectPr/></w:body>")),  # section
        ("word/styles.xml", _sub(r'w:val="22"', 'w:val="30"')),  # style part
    ],
)
def test_design_changes_are_rejected(resume, part, mutation):
    result = _apply(resume, [_edit(3, text="새 문구")])
    mutated = _mutate(result, part, mutation)
    assert mutated != result
    with pytest.raises(DesignViolation, match="이력서 디자인 보존 위반"):
        docx_guard.check(resume, mutated)


def test_pictures_must_stay(tmp_path):
    drawing = '<w:r><w:drawing><wp:inline xmlns:wp="urn:x"/></w:drawing></w:r>'
    base = tmp_path / "pic.docx"
    base.write_bytes(
        _mutate(
            make_resume_docx(tmp_path / "r.docx").read_bytes(),
            "word/document.xml",
            _sub(r"</w:p>", drawing + "</w:p>"),
        )
    )
    edits = [_edit(0, text="새 이름")]  # the picture shares this paragraph
    result = docx_doc.apply(base, parse_plan(session.plan(resume_edits=edits, row_order=[]), 5))
    docx_guard.check(base, result)
    assert _texts(result)[0] == "새 이름"
    lost = _mutate(result, "word/document.xml", _sub(r"<w:drawing>.*?</w:drawing>", ""))
    with pytest.raises(DesignViolation, match="drawing"):
        docx_guard.check(base, lost)
