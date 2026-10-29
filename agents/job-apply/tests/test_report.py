from datetime import date

from ja_support.meta import make_meta
from ja_support.session import JOB_SECTIONS
from job_apply import report
from job_apply.models import RenderIssue

TODAY = date(2026, 10, 27)


def test_completion_text():
    meta = make_meta(fit=72)
    meta.posting.company, meta.posting.role = "예시<회사>", "백엔드 개발자"
    meta.posting.deadline = date(2026, 11, 10)
    meta.posting.extra_urls = ["https://x.dev/2"]
    text = report.completion(
        meta, "# h\n" + JOB_SECTIONS, "agents/job-apply/applications/x", "요약 & 근거", TODAY
    )
    assert text.splitlines() == [
        "✅ 지원 자료 준비 완료 — 예시&lt;회사&gt; · 백엔드 개발자",
        "• 마감: 2026-11-10 (D-14)",
        "• 적합도: 72/100 — 요약 &amp; 근거",
        "• 공고 요약:",
        "    – Python 백엔드 API 개발",
        "    – PostgreSQL·Docker 경험 필요",
        "    – Kubernetes 우대",
        "• 폴더: agents/job-apply/applications/x",
        "• 렌더링: 문제 없음",
        "• 처리하지 않은 링크: https://x.dev/2",
        "제출은 직접 해 주세요.",
    ]


def test_low_fit_render_issues_and_deadlines():
    meta = make_meta(fit=30)
    meta.render.remaining_issues = [
        RenderIssue(slide=4, shape_id=7, kind="overflow", detail="+18pt")
    ]
    text = report.completion(meta, "", "f", None, TODAY)
    assert "• 적합도: ⚠️ 낮은 적합도 30/100" in text
    assert "• 렌더링: ⚠️ 남은 문제 1건 (슬라이드 4: 글자 넘침)" in text
    assert (
        "• 마감: 상시·미상" in text and "공고 요약" not in text and "처리하지 않은 링크" not in text
    )
    assert report.deadline_line(TODAY, TODAY) == "2026-10-27 (D-day)"


def test_other_texts_and_file_names():
    assert report.duplicate("agents/job-apply/applications/a", 65) == (
        "🔁 이미 처리한 공고예요 → agents/job-apply/applications/a (적합도 65/100)"
    )
    assert report.expired(date(2026, 10, 20)) == "⏰ 마감(2026-10-20)이 지나 처리하지 않았어요."
    assert report.body_request("HTTP 403").startswith(
        "❓ 공고 페이지를 가져오지 못했어요 (사유: HTTP 403)."
    )
    assert report.file_names("가상 테크", "백엔드/개발자") == (
        "가상-테크_백엔드개발자_resume.pdf",
        "가상-테크_백엔드개발자_portfolio.pdf",
    )
