"""US1 + US2 through the CLI: /tailor's deterministic steps with session outputs as fixtures."""

import json

from ja_support import session
from ja_support.samples import make_posting_html
from job_apply import sources
from job_apply.config import Paths

URL = "https://jobs.example.com/postings/123"


def _origin_hashes(root):
    paths = Paths(root)
    return sources.sha256(paths.resume), sources.sha256(paths.portfolio)


def _start(job, httpx_mock, url=URL):
    httpx_mock.add_response(url=url, text=make_posting_html("jsonld"))
    code, res, _ = job("fetch", url)
    assert code == 0 and res["fetch"] == "ok"
    code, init, _ = job(
        "init",
        res["id"],
        "--company",
        "가상테크",
        "--role",
        "백엔드 개발자",
        "--deadline",
        "2026-11-10",
    )
    assert code == 0, init
    return res["id"], job.root.parents[1] / init["folder"]


def test_tailor_end_to_end(job, httpx_mock):
    before = _origin_hashes(job.root)
    _id, folder = _start(job, httpx_mock)
    assert folder.name == "2026-10-27_가상테크_백엔드-개발자"
    session.write(folder)
    code, applied, out = job("apply", str(folder))
    assert code == 0, out
    assert applied["attempt"] == 1
    assert applied["previews"] == ["preview/resume-01.png", "preview/slide-02.png"]
    code, ver, out = job("verify", str(folder))
    assert code == 0 and ver["ok"] and ver["unresolved"] == [], out
    code, done, out = job("complete", str(folder))
    assert code == 0, out
    assert done == {"status": "done", "reply_ts": None, "fit_score": 72, "remaining_issues": 0}
    for name in (
        "job.md",
        "analysis.md",
        "tailor.json",
        "resume.docx",
        "resume.pdf",
        "portfolio.pptx",
        "portfolio.pdf",
        "changes.md",
        "preview/slide-02.png",
        "preview/resume-01.png",
        "base/render/portfolio.pdf",
        "base/render/resume.pdf",
        "base/render/resume-01.png",
        "base/resume.json",
    ):
        assert (folder / name).is_file(), name
    meta = json.loads((folder / "meta.json").read_text())
    assert meta["status"] == "done"
    assert _origin_hashes(job.root) == before
    assert not [r for r in httpx_mock.get_requests() if "slack.com" in str(r.url)]
    assert "제출은 직접 해 주세요." in out


def test_unsupported_claim_blocks_complete_until_acknowledged(job, httpx_mock):
    from ja_support.flow import ready

    folder = ready(job, httpx_mock, extra="- Kafka 기반 이벤트 처리\n")
    code, res, out = job("complete", str(folder))
    assert code == 9 and "근거가 확인되지 않은" in out
    assert json.loads((folder / "meta.json").read_text())["status"] == "in_progress"
    session.write_plan(
        folder,
        session.plan(
            acknowledged=[
                {
                    "file": "resume.docx",
                    "token": "Kafka",
                    "source": "resume.txt:L5",
                    "reason": "원본의 이벤트 처리 경험 표기",
                }
            ]
        ),
    )
    assert job("complete", str(folder))[0] == 0


def test_low_fit_is_flagged_in_summary(job, httpx_mock):
    from ja_support.flow import ready

    folder = ready(job, httpx_mock, score=35)
    code, res, out = job("complete", str(folder))
    assert code == 0 and "⚠️ 낮은 적합도 35/100" in out


def test_duplicate_url_needs_new(job, httpx_mock):
    from ja_support.flow import ready

    first = ready(job, httpx_mock)
    assert job("complete", str(first))[0] == 0
    snapshot = {p: p.read_bytes() for p in first.rglob("*") if p.is_file()}
    again = URL + "?utm_source=x"
    httpx_mock.add_response(url=again, text=make_posting_html("jsonld"))
    code, res, _ = job("fetch", again)
    assert res["duplicate_of"] == "agents/job-apply/applications/2026-10-27_가상테크_백엔드-개발자"
    code, res, out = job("init", res["id"], "--company", "가상테크", "--role", "백엔드 개발자")
    assert code == 6 and res["duplicate_of"].endswith("백엔드-개발자")
    code, res, _ = job(
        "init",
        res.get("id", "") or _last_id(job),
        "--company",
        "가상테크",
        "--role",
        "백엔드 개발자",
        "--new",
    )
    assert code == 0 and res["folder"].endswith("백엔드-개발자_2")
    assert snapshot == {p: p.read_bytes() for p in first.rglob("*") if p.is_file()}


def _last_id(job):
    inbox = job.root / ".job-state" / "inbox"
    return max(inbox.glob("t-*.json"), key=lambda p: p.stat().st_mtime).stem


def test_failed_folder_is_reused(job, httpx_mock):
    from ja_support.flow import start

    posting_id, folder = start(job, httpx_mock)
    assert job("fail", str(folder), "--step", "analysis", "--reason", "요건 추출 실패")[0] == 0
    assert json.loads((folder / "meta.json").read_text())["status"] == "failed"
    code, res, _ = job("init", posting_id, "--company", "가상테크", "--role", "백엔드 개발자")
    assert code == 0 and res["reused"] is True and job.root.parents[1] / res["folder"] == folder
    meta = json.loads((folder / "meta.json").read_text())
    assert meta["status"] == "in_progress" and meta["error"] is None


def test_done_folder_is_never_modified(job, httpx_mock):
    from ja_support.flow import ready

    folder = ready(job, httpx_mock)
    assert job("complete", str(folder))[0] == 0
    for cmd in (
        ("apply", str(folder)),
        ("note-issue", str(folder), "--slide", "1", "--detail", "x"),
    ):
        assert job(*cmd)[0] == 2
    assert job("complete", str(folder))[0] == 0  # idempotent


LONG = "아주 긴 메모 문장입니다 " * 6


def _small_edit(text):
    return [
        {
            "slide": 2,
            "shape_id": 4,
            "paragraph": 0,
            "text": text,
            "source": "portfolio.json:s2/sh4/p0",
            "reason": "메모 문구 조정",
        }
    ]


def test_render_loop_up_to_three_attempts(job, httpx_mock):
    from ja_support.flow import start

    _id, folder = start(job, httpx_mock)
    session.write(folder, tailor=session.plan(edits=_small_edit(LONG)))
    code, res, _ = job("apply", str(folder))
    assert code == 3 and res["attempt"] == 1
    assert [(i["slide"], i["shape_id"], i["kind"]) for i in res["issues"]] == [(2, 4, "overflow")]

    assert job("note-issue", str(folder), "--slide", "2", "--detail", "한 글자 고아 줄")[0] == 0
    session.write_plan(folder, session.plan(edits=_small_edit("짧은 메모")))
    code, res, _ = job("apply", str(folder))
    assert (
        code == 0 and res["attempt"] == 2 and res["issues"] == []
    )  # visual on re-applied slide cleared

    assert job("note-issue", str(folder), "--slide", "2", "--detail", "줄 간격이 어색함")[0] == 0
    session.write_plan(folder, session.plan(edits=_small_edit(LONG)))
    code, res, _ = job("apply", str(folder))
    assert code == 3 and res["attempt"] == 3
    code, res, out = job("apply", str(folder))
    assert code == 2 and "최대 3회" in out

    assert job("note-issue", str(folder), "--slide", "2", "--detail", "줄 간격이 어색함")[0] == 0
    changes = (folder / "changes.md").read_text()
    assert "시도 3/3" in changes and "글자 넘침" in changes and "줄 간격이 어색함" in changes
    code, done, _ = job("complete", str(folder))
    assert code == 0 and done["remaining_issues"] == 2


def test_longer_resume_is_an_issue_and_pages_can_be_noted(job, httpx_mock):
    from ja_support.flow import start

    _id, folder = start(job, httpx_mock)
    filler = [
        {
            "paragraph": 6,
            "op": {"kind": "insert_after", "text": "Docker 배포 파이프라인 구축"},
            "source": "resume.txt:L7",
            "reason": "테스트용 반복 문단",
        }
    ] * 60
    session.write(folder, tailor=session.plan(resume_edits=filler))
    code, res, _ = job("apply", str(folder))
    assert code == 3
    [issue] = res["issues"]
    assert (issue["file"], issue["slide"], issue["kind"]) == ("resume", 2, "overflow")
    assert res["previews"][:2] == ["preview/resume-01.png", "preview/resume-02.png"]

    session.write_plan(folder, session.plan())
    assert job("apply", str(folder))[0] == 0
    assert not (folder / "preview" / "resume-02.png").exists()
    assert job("note-issue", str(folder), "--page", "1", "--detail", "줄 바꿈이 어색함")[0] == 0
    assert "이력서 1쪽: 눈으로 확인 (줄 바꿈이 어색함)" in (folder / "changes.md").read_text()
