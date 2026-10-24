import io
import json
from datetime import timedelta

import anthropic
import httpx
import pytest

from nd_support import MAIN_HOOK, TEST_HOOK, FakeAnthropic, FakeResponse, make_selection
from news_digest import cli, history
from news_digest.models import RunStatus
from news_digest.normalize import article_id
from news_digest.pipeline import RunContext, run

EKS = "https://aws.amazon.com/blogs/aws/amazon-eks-kubernetes-1-34/"
ALL_FEEDS = ["aws_blog.xml", "aws_whats_new.xml", "hnrss.xml", "atom_blog.xml"]


@pytest.fixture
def ctx_factory(settings, sources, env, now, history_path):
    def make(llm, http, **kw):
        return RunContext(
            settings=settings,
            sources=sources,
            env=env,
            http=http,
            llm=llm,
            now=now,
            history_path=history_path,
            base_delay=0,
            out=io.StringIO(),
            **kw,
        )

    return make


def _sent(httpx_mock, url):
    return [json.loads(r.read()) for r in httpx_mock.get_requests(url=url)]


def _run(ctx_factory, llm, **kw):
    with httpx.Client() as http:
        return run(ctx_factory(llm, http, **kw))


def _refusal():
    return FakeResponse(None, stop_reason="refusal", stop_details={"category": "cyber"})


def _api_error():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIConnectionError(request=req)


@pytest.mark.parametrize(
    ("case", "feeds", "llm_responses", "main_status", "expected", "exit_code"),
    [
        (
            "all feeds fail",
            {f: {"status_code": 500} for f in ALL_FEEDS},
            [],
            None,
            RunStatus.COLLECT_FAILED,
            1,
        ),
        (
            "no new articles",
            {f: {"content": b"<rss version='2.0'><channel/></rss>"} for f in ALL_FEEDS},
            [],
            None,
            RunStatus.NO_NEW_ARTICLES,
            0,
        ),
        ("refusal", None, [_refusal()], None, RunStatus.SELECT_FAILED, 1),
        ("api error", None, [_api_error()], None, RunStatus.SELECT_FAILED, 1),
        (
            "invalid twice",
            None,
            [FakeResponse(None), FakeResponse(None)],
            None,
            RunStatus.SELECT_FAILED,
            1,
        ),
        ("post fails", None, ["eks"], 500, RunStatus.POST_FAILED, 1),
    ],
)
def test_failures_alert_test_channel_only(
    httpx_mock,
    mock_feeds,
    ctx_factory,
    history_path,
    case,
    feeds,
    llm_responses,
    main_status,
    expected,
    exit_code,
):
    mock_feeds(feeds)
    responses = [
        FakeResponse(make_selection(article_id(EKS))) if r == "eks" else r for r in llm_responses
    ]
    if main_status:
        httpx_mock.add_response(url=MAIN_HOOK, status_code=main_status, is_reusable=True)
    httpx_mock.add_response(url=TEST_HOOK, text="ok")

    result = _run(ctx_factory, FakeAnthropic(responses=responses))

    assert result.status == expected, case
    assert cli.exit_code(result) == exit_code
    [alert] = _sent(httpx_mock, TEST_HOOK)
    assert alert["text"] == f"⚠️ news-digest {expected}"
    main_posts = _sent(httpx_mock, MAIN_HOOK)
    assert main_posts == [] or main_status  # only the failed attempts when posting failed
    assert not history_path.exists()


def test_budget_exceeded_alerts_and_skips_llm(httpx_mock, mock_feeds, ctx_factory, settings):
    settings.budget.max_cost_usd_per_run = 0.01  # less than the max_tokens output reserve
    mock_feeds()
    httpx_mock.add_response(url=TEST_HOOK, text="ok")
    llm = FakeAnthropic()
    result = _run(ctx_factory, llm)
    assert result.status == RunStatus.BUDGET_EXCEEDED
    assert llm.parse_calls == []
    [alert] = _sent(httpx_mock, TEST_HOOK)
    assert "BUDGET_EXCEEDED" in alert["text"]
    assert _sent(httpx_mock, MAIN_HOOK) == []


def test_partial_collect_posts_and_warns(httpx_mock, mock_feeds, ctx_factory, history_path):
    mock_feeds({"atom_blog.xml": {"status_code": 503}, "aws_whats_new.xml": {"status_code": 404}})
    httpx_mock.add_response(url=MAIN_HOOK, text="ok")
    httpx_mock.add_response(url=TEST_HOOK, text="ok")
    llm = FakeAnthropic(responses=[FakeResponse(make_selection(article_id(EKS)))])

    result = _run(ctx_factory, llm)

    assert result.status == RunStatus.POSTED
    assert len(_sent(httpx_mock, MAIN_HOOK)) == 1
    [warning] = _sent(httpx_mock, TEST_HOOK)
    assert "partial collect: AWS What's New, Agents Blog" in json.dumps(warning, ensure_ascii=False)
    assert history.load(history_path).posts


def test_low_relevance_posts_and_warns(httpx_mock, mock_feeds, ctx_factory):
    mock_feeds()
    httpx_mock.add_response(url=MAIN_HOOK, text="ok")
    httpx_mock.add_response(url=TEST_HOOK, text="ok")
    llm = FakeAnthropic(
        responses=[FakeResponse(make_selection(article_id(EKS), low_relevance=True))]
    )
    result = _run(ctx_factory, llm)
    assert result.status == RunStatus.POSTED
    [warning] = _sent(httpx_mock, TEST_HOOK)
    assert "low relevance" in json.dumps(warning, ensure_ascii=False)


def test_alert_delivery_failure_is_logged_not_raised(httpx_mock, mock_feeds, ctx_factory, caplog):
    mock_feeds({f: {"status_code": 500} for f in ALL_FEEDS})
    httpx_mock.add_response(url=TEST_HOOK, status_code=500, is_reusable=True)
    result = _run(ctx_factory, FakeAnthropic())
    assert result.status == RunStatus.COLLECT_FAILED
    assert cli.exit_code(result) == 1
    assert any(r.getMessage() == "alert_failed" for r in caplog.records)


def test_unexpected_exception_alerts_and_exits_1(
    httpx_mock, mock_feeds, ctx_factory, history_path, now
):
    history_path.write_text("{not json")
    httpx_mock.add_response(url=TEST_HOOK, text="ok")
    result = _run(ctx_factory, FakeAnthropic())
    assert result.status is None
    assert cli.exit_code(result) == 1
    [alert] = _sent(httpx_mock, TEST_HOOK)
    assert alert["text"] == "⚠️ news-digest UNEXPECTED_ERROR"


def test_dry_run_failures_print_instead_of_sending(httpx_mock, mock_feeds, ctx_factory):
    mock_feeds({f: {"status_code": 500} for f in ALL_FEEDS})
    out = io.StringIO()
    with httpx.Client() as http:
        ctx = ctx_factory(FakeAnthropic(), http, dry_run=True)
        ctx.out = out
        result = run(ctx)
    assert result.status == RunStatus.COLLECT_FAILED
    assert _sent(httpx_mock, TEST_HOOK) == []
    assert "COLLECT_FAILED" in out.getvalue()


def test_already_posted_sends_no_alert(httpx_mock, ctx_factory, history_path, now):
    from news_digest.models import History, PostRecord

    record = PostRecord(
        article_id=article_id(EKS),
        url=EKS,
        title="t",
        title_ko="t",
        category="infra",
        source="s",
        posted_at=now - timedelta(minutes=1),
        posted_date_kst=(now + timedelta(hours=9)).date(),
    )
    history.save(history_path, History(posts=[record]), now=now)
    result = _run(ctx_factory, FakeAnthropic())
    assert result.status == RunStatus.ALREADY_POSTED
    assert cli.exit_code(result) == 0
    assert httpx_mock.get_requests() == []
