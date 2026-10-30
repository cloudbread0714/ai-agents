import json

from ja_support import session
from ja_support.flow import ready
from job_apply.verify import _in


def _verify(job, folder):
    code, res, out = job("verify", str(folder))
    assert code == 0, out
    return res


def test_clean_folder_passes(job, httpx_mock):
    folder = ready(job, httpx_mock)
    res = _verify(job, folder)
    assert res == {
        "ok": True,
        "missing": [],
        "problems": [],
        "unresolved": [],
        "acknowledged": [],
        "fit_score": 72,
    }
    assert "경고 없음" in (folder / "changes.md").read_text()
    assert json.loads((folder / "meta.json").read_text())["fit_score"] == 72


def test_missing_artifact(job, httpx_mock):
    folder = ready(job, httpx_mock)
    (folder / "resume.pdf").unlink()
    res = _verify(job, folder)
    assert not res["ok"] and res["missing"] == ["resume.pdf"]


def test_analysis_format(job, httpx_mock):
    folder = ready(job, httpx_mock)
    (folder / "analysis.md").write_text("---\nfit_score: 120\n---\n## 일치하는 점\n")
    problems = _verify(job, folder)["problems"]
    assert any("fit_score" in p for p in problems)
    assert any("summary" in p for p in problems)
    assert any("섹션" in p for p in problems)


def test_job_sections_required(job, httpx_mock):
    folder = ready(job, httpx_mock)
    job_md = folder / "job.md"
    job_md.write_text(job_md.read_text().replace("## 우대 사항", "## 우대"))
    assert any("## 우대 사항" in p for p in _verify(job, folder)["problems"])


def test_base_hash_must_match_meta(job, httpx_mock):
    folder = ready(job, httpx_mock)
    (folder / "base" / "resume.docx").write_bytes(b"changed")
    assert any("base/resume.docx" in p for p in _verify(job, folder)["problems"])


def test_provenance_warnings_and_acknowledgement(job, httpx_mock):
    folder = ready(
        job, httpx_mock, extra="- Kafka 기반 이벤트 처리 40% 단축\n- Kubernetes 클러스터 운영\n"
    )
    res = _verify(job, folder)
    found = {(w["file"], w["token"], w["kind"]) for w in res["unresolved"]}
    assert ("resume.docx", "Kafka", "tech") in found
    assert ("resume.docx", "40%", "number") in found
    assert ("resume.docx", "Kubernetes", "gap") in found
    assert res["ok"]  # warnings never fail verify itself

    data = session.plan(
        acknowledged=[
            {
                "file": "resume.docx",
                "token": "kafka",
                "source": "resume.txt:L5",
                "reason": "테스트용 해명 사유",
            }
        ]
    )
    session.write_plan(folder, data)
    res = _verify(job, folder)
    assert [w["token"] for w in res["acknowledged"]] == ["Kafka"]
    assert "Kafka" not in [w["token"] for w in res["unresolved"]]
    changes = (folder / "changes.md").read_text()
    assert (
        "해명됨: resume.docx `Kafka` → resume.txt:L5" in changes
        and "해명 안 됨: resume.docx `40%`" in changes
    )


def test_units_glued_to_numbers_match_the_source():
    corpus = "위치 0.10 (30km 감쇠), 512mb 메모리 제한"
    assert _in(corpus, "km") and _in(corpus, "MB")
    assert not _in(corpus, "GB") and not _in("kmz 파일", "km")


def test_portfolio_text_is_checked_too(job, httpx_mock):
    folder = ready(job, httpx_mock)
    edits = [
        {
            "slide": 2,
            "shape_id": 4,
            "paragraph": 0,
            "text": "Terraform 도입",
            "source": "portfolio.json:s2/sh4/p0",
            "reason": "테스트용 근거 없는 문구",
        }
    ]
    session.write_plan(folder, session.plan(edits=edits))
    assert job("apply", str(folder))[0] == 0
    found = {(w["file"], w["token"]) for w in _verify(job, folder)["unresolved"]}
    assert ("portfolio.pptx", "Terraform") in found
