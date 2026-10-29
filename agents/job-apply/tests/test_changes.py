from ja_support import session
from ja_support.meta import make_meta
from job_apply.changes import cell, render
from job_apply.models import RenderIssue, parse_plan


def test_sections_in_order_and_cells_escaped():
    meta = make_meta()
    meta.render.attempts = 2
    meta.render.remaining_issues = [
        RenderIssue(slide=2, shape_id=4, kind="overflow", detail="+12pt")
    ]
    data = session.plan()
    data["resume"]["changes"][0]["after"] = "A | B\n둘째 줄"
    plan = parse_plan(data, 5)
    dump = {
        "slides": [{"slide": 2, "shapes": [{"shape_id": 2, "paragraphs": [{"text": "원래 문구"}]}]}]
    }
    warnings = {
        "unresolved": [{"file": "resume.md", "token": "Kafka", "kind": "tech"}],
        "acknowledged": [
            {
                "file": "resume.md",
                "token": "PG",
                "kind": "tech",
                "source": "resume.txt:L6",
                "reason": "PostgreSQL 약칭",
            }
        ],
    }
    text = render(meta, plan, dump, warnings, 3)
    heads = [ln for ln in text.splitlines() if ln.startswith("## ")]
    assert heads == [
        "## 사용한 원본",
        "## 이력서 변경",
        "## 포트폴리오 슬라이드 순서",
        "## 포트폴리오 문구 변경",
        "## 렌더링 점검",
        "## 근거 검사 경고",
    ]
    assert "| resume.pdf | aaaaaaaaaaaa | 2026-10-27T00:00:00+00:00 |" in text
    assert "A \\| B<br>둘째 줄" in text
    assert "| 2 / shape 2 / 문단 0 | 원래 문구 | 핵심 역량: Python API 서버 |" in text
    assert "시도 2/3" in text and "슬라이드 2 shape 4: 글자 넘침 (+12pt)" in text
    assert (
        "해명 안 됨: resume.md `Kafka`" in text and "해명됨: resume.md `PG` → resume.txt:L6" in text
    )


def test_cell():
    assert cell(None) == "" and cell("a|b\r\nc") == "a\\|b<br>c"
