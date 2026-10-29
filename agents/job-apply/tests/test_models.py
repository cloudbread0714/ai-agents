import json
from datetime import date
from pathlib import Path

import pytest

from ja_support import session
from job_apply.errors import PlanError
from job_apply.models import SCHEMA_PATH, Meta, Posting, RenderIssue, parse_plan

CONTRACT = (
    Path(__file__).resolve().parents[3]
    / "specs/003-job-tailor-applications/contracts/tailor-plan.schema.json"
)


def test_packaged_schema_equals_contract():
    assert json.loads(SCHEMA_PATH.read_text()) == json.loads(CONTRACT.read_text())


def test_posting_deadline_and_expired():
    p = Posting(
        id="t-1", origin="direct", url_key="k", fetch={"status": "ok"}, deadline="2026-10-26"
    )
    assert p.expired(date(2026, 10, 27)) and not p.expired(date(2026, 10, 26))
    assert not Posting(id="t-1", origin="direct", url_key="k", fetch={"status": "ok"}).expired(
        date(2026, 1, 1)
    )
    with pytest.raises(ValueError):
        Posting(id="t", origin="direct", url_key="k", fetch={"status": "ok"}, deadline="11/10")


def _meta(**kw):
    base = {
        "schema": 1,
        "status": "in_progress",
        "created_at": "2026-10-27T10:00:00+09:00",
        "posting": {"id": "t", "origin": "direct", "url_key": "k", "company": "c", "role": "r"},
        "sources": {
            "resume": {"sha256": "a", "mtime": "2026-10-27T00:00:00Z"},
            "portfolio": {"sha256": "b", "mtime": "2026-10-27T00:00:00Z"},
        },
    }
    return Meta.model_validate({**base, **kw})


@pytest.mark.parametrize("bad", [{"status": "archived"}, {"fit_score": 101}, {"fit_score": -1}])
def test_meta_rules(bad):
    with pytest.raises(ValueError):
        _meta(**bad)


def test_meta_transitions():
    meta = _meta()
    meta.move("failed")
    meta.move("in_progress")
    meta.move("done")
    with pytest.raises(ValueError):
        meta.move("in_progress")
    assert json.loads(meta.dump())["schema"] == 1


def test_render_issue_kinds():
    RenderIssue(slide=1, kind="visual", detail="x")
    with pytest.raises(ValueError):
        RenderIssue(slide=1, kind="ugly", detail="x")


def test_plan_valid():
    plan = parse_plan(session.plan(), 5)
    assert plan.portfolio.edits[0].runs == ["핵심 역량: ", "Python API 서버"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["portfolio"].update(slide_order=[1, 2, 3, 4]),
        lambda d: d["portfolio"].update(slide_order=[1, 1, 3, 4, 5]),
        lambda d: d["portfolio"]["edits"][0].update(text="x"),  # runs + text
        lambda d: d["portfolio"]["edits"][0].pop("runs"),  # none of text/runs/op
        lambda d: d["portfolio"]["edits"][0].update(source=""),
        lambda d: d["portfolio"]["edits"][0].update(source="somewhere"),
        lambda d: d["portfolio"]["edits"][0].update(slide=9),
        lambda d: d["resume"]["changes"][0].pop("reason"),
        lambda d: d.update(extra=1),
        lambda d: (
            d["portfolio"]["edits"][0].update(op={"kind": "insert_after"})
            or d["portfolio"]["edits"][0].pop("runs")
        ),
    ],
)
def test_plan_rules(mutate):
    data = session.plan()
    mutate(data)
    with pytest.raises(PlanError):
        parse_plan(data, 5)
