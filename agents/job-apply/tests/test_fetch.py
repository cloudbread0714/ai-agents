import httpx
import pytest

from ja_support.samples import make_posting_html
from job_apply.config import FetchConfig
from job_apply.fetch import fetch

URL = "https://jobs.example.com/p/1"
CFG = FetchConfig(min_chars=400)


def _fetch(httpx_mock, **resp):
    httpx_mock.add_response(url=URL, **resp)
    with httpx.Client() as client:
        return fetch(URL, CFG, client, base_delay=0)


def test_json_ld_preferred(httpx_mock):
    got = _fetch(httpx_mock, text=make_posting_html("jsonld"))
    assert got.status == "ok" and got.text.startswith("백엔드 개발자\n가상테크\n마감: 2026-11-10")
    assert "메뉴" not in got.text


def test_next_data(httpx_mock):
    got = _fetch(httpx_mock, text=make_posting_html("next_data"))
    assert got.status == "ok" and "데이터 엔지니어" in got.text and "Kubernetes" in got.text


def test_plain_page_via_trafilatura(httpx_mock):
    got = _fetch(httpx_mock, text=make_posting_html("plain"))
    assert got.status == "ok" and "PostgreSQL" in got.text


@pytest.mark.parametrize(
    ("kind", "reason"), [("too_short", "본문이 너무 짧음"), ("login_wall", "로그인 필요")]
)
def test_unusable_pages_fail_with_reason(httpx_mock, kind, reason):
    got = _fetch(httpx_mock, text=make_posting_html(kind))
    assert (got.status, got.reason) == ("failed", reason)


@pytest.mark.parametrize(
    ("content_type", "meta"),
    [("text/html", ""), ("text/html", '<meta charset="euc-kr">')],
)
def test_undeclared_or_meta_euc_kr_page_decodes(httpx_mock, content_type, meta):
    page = make_posting_html("plain").replace("<html>", f"<html><head>{meta}</head>", 1)
    assert meta in page
    got = _fetch(httpx_mock, content=page.encode("cp949"), headers={"content-type": content_type})
    assert got.status == "ok" and "\ufffd" not in got.text and "백엔드" in got.text


def test_403_fails_without_retry(httpx_mock):
    got = _fetch(httpx_mock, status_code=403)
    assert (got.status, got.reason) == ("failed", "HTTP 403")
    assert len(httpx_mock.get_requests()) == 1


def test_5xx_and_timeouts_retried_three_times(httpx_mock):
    httpx_mock.add_response(url=URL, status_code=502)
    httpx_mock.add_exception(httpx.ReadTimeout("slow"))
    got = _fetch(httpx_mock, status_code=503)
    assert (got.status, got.reason) == ("failed", "HTTP 503")
    assert len(httpx_mock.get_requests()) == 3


def test_text_file_is_skipped(job, tmp_path):
    from ja_support.samples import posting_text

    body = tmp_path / "in.txt"
    body.write_text(posting_text())
    code, res, _ = job("fetch", "--text-file", str(body))
    assert code == 0 and res["fetch"] == "skipped" and res["id"].startswith("t-")
    assert (job.root.parents[1] / res["text_path"]).read_text().strip() == posting_text().strip()


def test_cli_fetch_failure_is_exit_0(job, httpx_mock):
    httpx_mock.add_response(url=URL, status_code=403)
    code, res, out = job("fetch", URL)
    assert code == 0 and res["fetch"] == "failed" and res["reason"] == "HTTP 403"
