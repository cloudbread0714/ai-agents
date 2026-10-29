import pytest

from ja_support import session
from ja_support.fake_render import render
from ja_support.samples import make_portfolio_pptx
from job_apply.layout_check import find_issues, new_issues
from job_apply.models import parse_plan
from job_apply.pptx_apply import apply


@pytest.fixture
def base(tmp_path):
    deck = make_portfolio_pptx(tmp_path / "base.pptx")
    return deck, render(deck, tmp_path / "base-render")


def _result(tmp_path, deck, edits, order=None):
    plan = parse_plan(session.plan(edits=edits, order=order), 5)
    out = tmp_path / "result.pptx"
    out.write_bytes(apply(deck, plan))
    return plan, out, render(out, tmp_path / "result-render")


def _edit(slide, shape_id, text):
    return {
        "slide": slide,
        "shape_id": shape_id,
        "paragraph": 0,
        "text": text,
        "source": f"portfolio.json:s{slide}/sh{shape_id}/p0",
        "reason": "길이 확인용 변경",
    }


def test_base_has_only_the_designed_overlap(base):
    deck, pdf = base
    issues = find_issues(deck, pdf, 4)
    assert [(i.slide, i.kind) for i in issues] == [(4, "overlap")]


def test_overflow_reported_with_points_and_base_overlap_excluded(tmp_path, base):
    deck, pdf = base
    plan, out, out_pdf = _result(tmp_path, deck, [_edit(2, 4, "아주 긴 메모 문장입니다 " * 6)])
    issues = new_issues(
        find_issues(out, out_pdf, 4), find_issues(deck, pdf, 4), plan.portfolio.slide_order
    )
    assert [(i.slide, i.shape_id, i.kind) for i in issues] == [(2, 4, "overflow")]
    assert issues[0].detail.startswith("+") and issues[0].detail.endswith("pt")


def test_short_text_has_no_issue(tmp_path, base):
    deck, pdf = base
    plan, out, out_pdf = _result(tmp_path, deck, [_edit(2, 4, "짧은 메모")])
    assert (
        new_issues(
            find_issues(out, out_pdf, 4), find_issues(deck, pdf, 4), plan.portfolio.slide_order
        )
        == []
    )


def test_offslide_and_new_overlap(tmp_path, base):
    deck, pdf = base
    long = "슬라이드 아래로 넘치는 긴 설명 문장 " * 80
    plan, out, out_pdf = _result(tmp_path, deck, [_edit(2, 2, long)])
    kinds = {
        i.kind
        for i in new_issues(
            find_issues(out, out_pdf, 4), find_issues(deck, pdf, 4), plan.portfolio.slide_order
        )
    }
    assert {"overflow", "offslide", "overlap"} <= kinds


def test_base_issues_follow_reordered_slides(tmp_path, base):
    deck, pdf = base
    plan, out, out_pdf = _result(tmp_path, deck, [_edit(2, 4, "짧게")], order=[4, 1, 2, 3, 5])
    found = find_issues(out, out_pdf, 4)
    assert [(i.slide, i.kind) for i in found] == [(1, "overlap")]  # base slide 4 now first
    assert new_issues(found, find_issues(deck, pdf, 4), plan.portfolio.slide_order) == []
