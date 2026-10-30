import httpx
import pytest

from ja_support.samples import make_posting_html
from job_apply.config import FetchConfig
from job_apply.fetch import detail_url, fetch

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


SARAMIN = "https://www.saramin.co.kr/zf_user/jobs/relay/view?isMypage=no&rec_idx=123&view_type=x"
SARAMIN_DETAIL = "https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx=123"
SHELL = (
    '<html><head><meta property="og:title" content="[가상테크] 백엔드 개발자 채용">'
    '<meta property="og:description" content="가상테크, 마감일:2026-11-10"></head>'
    "<body><p>개인정보 보호 안내 문구가 여기에 길게 들어갑니다.</p></body></html>"
)


@pytest.mark.parametrize(
    ("url", "detail"),
    [
        (SARAMIN, SARAMIN_DETAIL),
        (
            "https://www.jobkorea.co.kr/Recruit/GI_Read/50185224?Oem_Code=C1",
            "https://www.jobkorea.co.kr/Recruit/GI_Read_Comt_Ifrm?Gno=50185224",
        ),
        ("https://www.saramin.co.kr/zf_user/company-info", None),
        (URL, None),
    ],
)
def test_detail_url(url, detail):
    assert detail_url(url) == detail


def _board(httpx_mock, detail_page):
    httpx_mock.add_response(url=SARAMIN, text=SHELL)
    httpx_mock.add_response(url=SARAMIN_DETAIL, text=detail_page)
    with httpx.Client() as client:
        return fetch(SARAMIN, CFG, client, base_delay=0)


def test_board_body_comes_from_the_detail_page(httpx_mock):
    got = _board(httpx_mock, make_posting_html("plain"))
    assert got.status == "ok" and "PostgreSQL" in got.text and "개인정보" not in got.text
    assert got.text.startswith("[가상테크] 백엔드 개발자 채용\n가상테크, 마감일:2026-11-10")


def _png(height: int) -> bytes:
    import pymupdf

    return pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, height), True).tobytes("png")


IMAGE_BODY = '<html><body><img src="/i/a.png"><img src="data:x"><img src="/i/b.png"></body></html>'
IMG_A, IMG_B = "https://www.saramin.co.kr/i/a.png", "https://www.saramin.co.kr/i/b.png"


def test_image_body_is_downloaded(httpx_mock):
    httpx_mock.add_response(url=IMG_A, content=_png(10), headers={"content-type": "image/png"})
    httpx_mock.add_response(url=IMG_B, content=b"<html>", headers={"content-type": "text/html"})
    got = _board(httpx_mock, IMAGE_BODY)
    assert (got.status, got.reason, len(got.images)) == ("images", "본문이 이미지로 게시됨", 1)
    assert got.text.startswith("[가상테크] 백엔드 개발자 채용")


def test_image_body_that_cannot_be_downloaded_fails(httpx_mock):
    httpx_mock.add_response(url=IMG_A, status_code=404)
    httpx_mock.add_response(url=IMG_B, status_code=404)
    got = _board(httpx_mock, IMAGE_BODY)
    assert (got.status, got.reason) == ("failed", "본문 이미지를 받지 못함 (이미지 2개)")


def test_cli_saves_tall_images_in_pieces(job, httpx_mock):
    from job_apply.images import PIECE_HEIGHT

    httpx_mock.add_response(url=SARAMIN, text=SHELL)
    httpx_mock.add_response(url=SARAMIN_DETAIL, text=IMAGE_BODY)
    tall = _png(PIECE_HEIGHT * 2 + 5)
    httpx_mock.add_response(url=IMG_A, content=tall, headers={"content-type": "image/png"})
    httpx_mock.add_response(url=IMG_B, content=_png(10), headers={"content-type": "image/png"})
    code, res, out = job("fetch", SARAMIN)
    assert code == 0 and res["fetch"] == "images" and "4장" in out
    assert [p.rsplit("/", 1)[1] for p in res["images"]] == [
        "01-1.png",
        "01-2.png",
        "01-3.png",
        "02-1.png",
    ]
    assert all((job.root.parents[1] / p).is_file() for p in res["images"])
