import io
import json

import httpx

from nd_support import MAIN_HOOK, TEST_HOOK, FakeAnthropic, FakeResponse, make_selection
from news_digest.models import RunStatus
from news_digest.normalize import article_id
from news_digest.pipeline import RunContext, run

EKS = "https://aws.amazon.com/blogs/aws/amazon-eks-kubernetes-1-34/"


def _ctx(settings, sources, env, now, history_path, llm, http, **kw) -> RunContext:
    return RunContext(
        settings=settings,
        sources=sources,
        env=env,
        http=http,
        llm=llm,
        now=now,
        history_path=history_path,
        base_delay=0,
        **kw,
    )


def _posted(httpx_mock, url):
    return [json.loads(r.read()) for r in httpx_mock.get_requests(url=url)]


def test_posts_exactly_one_formatted_message_to_main(
    httpx_mock, mock_feeds, settings, sources, env, now, history_path
):
    mock_feeds()
    httpx_mock.add_response(url=MAIN_HOOK, text="ok")
    llm = FakeAnthropic(responses=[FakeResponse(make_selection(article_id(EKS)))])

    with httpx.Client() as http:
        result = run(_ctx(settings, sources, env, now, history_path, llm, http))

    assert result.status == RunStatus.POSTED
    assert result.actual_cost_usd is not None and result.actual_cost_usd > 0
    [post] = _posted(httpx_mock, MAIN_HOOK)
    assert _posted(httpx_mock, TEST_HOOK) == []
    blocks = post["blocks"]
    assert blocks[0]["text"]["text"].startswith("📰 ")
    assert "*내용*" in blocks[1]["text"]["text"]
    assert "*나에게 적용할 점*" in blocks[2]["text"]["text"]
    assert EKS in blocks[3]["text"]["text"]
    # EKS appears in both the AWS blog and HN feeds; only one candidate is sent
    sent = llm.parse_calls[0]["messages"][0]["content"]
    assert sent.count(article_id(EKS)) == 1
    assert result.candidate_count == 6  # 7 items, EKS duplicated across feeds


def test_dry_run_prints_post_and_sends_nothing(
    httpx_mock, mock_feeds, settings, sources, env, now, history_path
):
    mock_feeds()
    llm = FakeAnthropic(responses=[FakeResponse(make_selection(article_id(EKS)))])
    out = io.StringIO()

    with httpx.Client() as http:
        result = run(
            _ctx(settings, sources, env, now, history_path, llm, http, dry_run=True, out=out)
        )

    assert result.status == RunStatus.POSTED
    assert _posted(httpx_mock, MAIN_HOOK) == [] and _posted(httpx_mock, TEST_HOOK) == []
    printed = out.getvalue()
    assert "📰 EKS" in printed and "• Amazon EKS가" in printed and EKS in printed


def test_target_test_posts_to_test_channel(
    httpx_mock, mock_feeds, settings, sources, env, now, history_path
):
    mock_feeds()
    httpx_mock.add_response(url=TEST_HOOK, text="ok")
    llm = FakeAnthropic(responses=[FakeResponse(make_selection(article_id(EKS)))])

    with httpx.Client() as http:
        result = run(_ctx(settings, sources, env, now, history_path, llm, http, target="test"))

    assert result.status == RunStatus.POSTED
    [post] = _posted(httpx_mock, TEST_HOOK)
    assert post["text"].startswith("[TEST] ")
    assert _posted(httpx_mock, MAIN_HOOK) == []
