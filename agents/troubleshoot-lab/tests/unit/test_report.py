import shutil
from pathlib import Path

from tl_support import ev, measured, progress_of, scenario_spec
from troubleshoot_lab import progress as prog
from troubleshoot_lab import report as rep
from troubleshoot_lab.models import Scenario

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "report.md"


def _repo(tmp_path):
    t = tmp_path / rep.TEMPLATE_REL
    t.parent.mkdir(parents=True)
    shutil.copy(TEMPLATE, t)
    return tmp_path


def _scenario(n_questions=2):
    spec = scenario_spec(
        "site-down", no="3", interview=[f"질문 {i}?" for i in range(1, n_questions + 1)]
    )
    return Scenario.model_validate(spec)


def _attempt(*extra, end="scenario_solved"):
    events = [
        ev("scenario_started", "site-down", 0, attempt=1),
        measured(
            "site-down",
            1,
            1,
            "baseline",
            avg_ms=10.0,
            p95_ms=20.0,
            rps=100.0,
            error_rate=0.0,
            requests=500,
            cpu_avg_pct=5.0,
            cpu_max_pct=9.5,
            mem_max_mib=60.0,
        ),
        ev("fault_injected", "site-down", 2, attempt=1),
        measured(
            "site-down",
            3,
            1,
            "fault",
            avg_ms="not_applicable",
            p95_ms="not_applicable",
            rps=50.0,
            error_rate=1.0,
            requests=250,
        ),
        ev("hint_opened", "site-down", 4, attempt=1, level=1),
        ev(end, "site-down", 5, attempt=1, hints_used=1),
        *extra,
    ]
    return prog.attempts(progress_of(*events))[0]


def test_draft_path_header_table_and_questions(tmp_path):
    repo = _repo(tmp_path)
    rel, created = rep.create_draft(_attempt(), _scenario(), repo)
    assert created and str(rel) == "agents/troubleshoot-lab/docs/reports/2026-10-26-site-down-1.md"
    text = (repo / rel).read_text()
    assert "# 시나리오 site-down" in text
    assert "시나리오 #3 · 분야 ② 리눅스 서버 · 시도 1 · 결과 해결 · 힌트 1개 사용" in text
    assert "| 평균 응답 시간 (ms) | 10.0 | 해당 없음 | 측정하지 않음 |" in text
    assert "| 오류율 (%) | 0.0 | 100.0 | 측정하지 않음 |" in text
    assert "| CPU 평균 / 최대 (%) | 5.0 / 9.5 | 측정 불가 / 측정 불가 | 측정하지 않음 |" in text
    assert "### Q1. 질문 1?" in text and "### Q2. 질문 2?" in text
    assert "개인정보나 비밀값을 쓰지 마세요" in text
    for section in rep.REQUIRED:
        assert f"## {section}\n<!-- 직접 작성" in text  # left for the learner


def test_skipped_measurement_shows_reason(tmp_path):
    repo = _repo(tmp_path)
    attempt = _attempt()
    attempt.measurements["after"] = ev(
        "measured",
        "site-down",
        6,
        attempt=1,
        phase="after",
        metrics={k: {"status": "skipped"} for k in attempt.measurements["baseline"].metrics},
        skip_reason="이미지 다운로드 실패",
    )
    rel, _ = rep.create_draft(attempt, _scenario(), repo)
    assert "측정 생략(이미지 다운로드 실패)" in (repo / rel).read_text()


def test_existing_report_is_not_overwritten(tmp_path):
    repo = _repo(tmp_path)
    rel, _ = rep.create_draft(_attempt(), _scenario(), repo)
    (repo / rel).write_text("내가 쓴 내용")
    rel2, created = rep.create_draft(_attempt(), _scenario(), repo)
    assert rel2 == rel and not created
    assert (repo / rel).read_text() == "내가 쓴 내용"


def _fill(text, *, skip=(), rename=None):
    for section in rep.REQUIRED:
        if section not in skip:
            text = text.replace(f"## {section}\n", f"## {section}\n내용 {section}\n", 1)
    text = text.replace("### Q1. 질문 1?\n", "### Q1. 질문 1?\n답 1\n")
    if "Q2" not in skip:
        text = text.replace("### Q2. 질문 2?\n", "### Q2. 질문 2?\n답 2\n")
    if rename:
        text = text.replace(*rename)
    return text


def test_done_check(tmp_path):
    repo = _repo(tmp_path)
    rel, _ = rep.create_draft(_attempt(), _scenario(), repo)
    path = repo / rel
    draft = path.read_text()
    missing, answered = rep.check_done(path, _scenario())
    assert missing[:5] == list(rep.REQUIRED) and answered == 0  # comments-only counts as empty

    path.write_text(_fill(draft, skip=("원인", "Q2")))
    missing, answered = rep.check_done(path, _scenario())
    assert missing == ["원인", "면접 질문 답변 Q2"] and answered == 1

    path.write_text(_fill(draft, rename=("## 재발 방지", "## 개선점")))
    assert rep.check_done(path, _scenario())[0] == ["재발 방지"]

    path.write_text(_fill(draft))
    assert rep.check_done(path, _scenario()) == ([], 2)


def test_status(tmp_path):
    repo = _repo(tmp_path)
    running = prog.attempts(progress_of(ev("scenario_started", "site-down", 0, attempt=1)))[0]
    assert rep.status(running, repo) == "none"
    assert rep.status(_attempt(), repo) == "missing"
    rel, _ = rep.create_draft(_attempt(), _scenario(), repo)
    assert rep.status(_attempt(), repo) == "draft"
    done = _attempt(ev("report_completed", "site-down", 9, attempt=1, report=str(rel), answered=2))
    assert rep.status(done, repo) == "done"
    (repo / rel).unlink()
    assert rep.status(done, repo) == "missing"  # deleted report counts as not written
    assert rep.status(_attempt(end="scenario_gave_up"), repo) == "missing"
