from ja_support import session
from ja_support.meta import make_meta
from job_apply.changes import cell, render
from job_apply.models import RenderIssue, parse_plan


def test_sections_in_order_and_cells_escaped():
    meta = make_meta()
    meta.render.attempts = 2
    meta.render.remaining_issues = [
        RenderIssue(file="resume", slide=2, kind="overflow", detail="원본 1쪽보다 길어짐(2쪽)"),
        RenderIssue(slide=2, shape_id=4, kind="overflow", detail="+12pt"),
    ]
    data = session.plan()
    data["resume"]["edits"][0]["text"] = "A | B\n둘째 줄"
    plan = parse_plan(data, 5)
    resume = {"paragraphs": [{"text": f"p{i}", "table": None} for i in range(4)]}
    resume["paragraphs"][4:] = [{"text": "원래 경력", "table": 1, "row": 1, "cell": 0}]
    dump = {
        "slides": [{"slide": 2, "shapes": [{"shape_id": 2, "paragraphs": [{"text": "원래 문구"}]}]}]
    }
    warnings = {
        "unresolved": [{"file": "resume.docx", "token": "Kafka", "kind": "tech"}],
        "acknowledged": [
            {
                "file": "resume.docx",
                "token": "PG",
                "kind": "tech",
                "source": "resume.txt:L6",
                "reason": "PostgreSQL 약칭",
            }
        ],
    }
    text = render(meta, plan, dump, resume, warnings, 3)
    heads = [ln for ln in text.splitlines() if ln.startswith("## ")]
    assert heads == [
        "## 사용한 원본",
        "## 이력서 문구 변경",
        "## 이력서 표 행 순서",
        "## 포트폴리오 슬라이드 순서",
        "## 포트폴리오 문구 변경",
        "## 렌더링 점검",
        "## 근거 검사 경고",
    ]
    assert "| resume.docx | aaaaaaaaaaaa | 2026-10-27T00:00:00+00:00 |" in text
    assert "| 4 (표 1 / 행 1 / 칸 0) | 원래 경력 | A \\| B<br>둘째 줄 | resume.txt:L5 |" in text
    assert "| 1 | 0, 2, 1, 3 | PostgreSQL 항목을 위로 |" in text
    assert "| 2 / shape 2 / 문단 0 | 원래 문구 | 핵심 역량: Python API 서버 |" in text
    assert "시도 2/3" in text and "슬라이드 2 shape 4: 글자 넘침 (+12pt)" in text
    assert "이력서 2쪽: 글자 넘침 (원본 1쪽보다 길어짐(2쪽))" in text
    assert (
        "해명 안 됨: resume.docx `Kafka`" in text
        and "해명됨: resume.docx `PG` → resume.txt:L6" in text
    )


def test_cell():
    assert cell(None) == "" and cell("a|b\r\nc") == "a\\|b<br>c"
