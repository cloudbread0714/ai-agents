"""Run the deterministic /tailor steps up to a ready-to-verify folder."""

from __future__ import annotations

from pathlib import Path

from ja_support import session
from ja_support.samples import make_posting_html

URL = "https://jobs.example.com/postings/123"


def start(job, httpx_mock, url: str = URL, *extra: str) -> tuple[str, Path]:
    httpx_mock.add_response(url=url, text=make_posting_html("jsonld"))
    code, res, out = job("fetch", url)
    assert code == 0, out
    code, init, out = job(
        "init",
        res["id"],
        "--company",
        "가상테크",
        "--role",
        "백엔드 개발자",
        "--deadline",
        "2026-11-10",
        *extra,
    )
    assert code == 0, out
    return res["id"], job.root.parents[1] / init["folder"]


def ready(job, httpx_mock, **write_kw) -> Path:
    _id, folder = start(job, httpx_mock)
    session.write(folder, **write_kw)
    assert job("resume-pdf", str(folder))[0] == 0
    code, _res, out = job("apply", str(folder))
    assert code == 0, out
    return folder
