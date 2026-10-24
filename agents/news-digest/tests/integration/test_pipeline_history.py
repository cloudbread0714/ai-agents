import io
import logging
from datetime import timedelta

import httpx
import pytest

from nd_support import (
    MAIN_HOOK,
    TEST_HOOK,
    FakeAnthropic,
    FakeResponse,
    candidate_ids,
    make_selection,
)
from news_digest import history
from news_digest.models import History, PostRecord, RunStatus
from news_digest.normalize import article_id, normalize_url
from news_digest.pipeline import RunContext, run

EKS = "https://aws.amazon.com/blogs/aws/amazon-eks-kubernetes-1-34/"
MCP = "https://www.example.dev/posts/mcp-servers"
AGENTS = "https://agents.example.com/posts/reliable-agents/"


def _record(url, posted_at, category="infra") -> PostRecord:
    return PostRecord(
        article_id=article_id(url),
        url=normalize_url(url),
        title="t",
        title_ko="제목",
        category=category,
        source="s",
        posted_at=posted_at,
        posted_date_kst=(posted_at + timedelta(hours=9)).date(),
    )


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


def _seed(path, *records):
    history.save(path, History(posts=list(records)), now=records[-1].posted_at)


def test_already_posted_article_excluded_and_post_recorded(
    httpx_mock, mock_feeds, ctx_factory, history_path, now
):
    _seed(history_path, _record(EKS, now - timedelta(days=1)))
    mock_feeds()
    httpx_mock.add_response(url=MAIN_HOOK, text="ok")
    llm = FakeAnthropic(responses=[FakeResponse(make_selection(article_id(MCP), "ai_agent"))])

    with httpx.Client() as http:
        result = run(ctx_factory(llm, http))

    assert result.status == RunStatus.POSTED
    assert article_id(EKS) not in candidate_ids(llm.parse_calls[0])
    saved = history.load(history_path)
    assert [p.article_id for p in saved.posts] == [article_id(EKS), article_id(MCP)]
    latest = saved.posts[-1]
    assert latest.url == normalize_url(MCP)
    assert latest.category == "ai_agent"
    assert str(latest.posted_date_kst) == "2026-10-26"
    assert latest.source == "Hacker News"


def test_same_article_in_two_feeds_counts_as_posted(
    httpx_mock, mock_feeds, ctx_factory, history_path, now
):
    # posted earlier via HN with a different URL form; the AWS blog copy must be excluded too
    _seed(history_path, _record(EKS + "?utm_source=hn", now - timedelta(days=1)))
    mock_feeds()
    httpx_mock.add_response(url=MAIN_HOOK, text="ok")
    llm = FakeAnthropic(responses=[FakeResponse(make_selection(article_id(MCP), "ai_agent"))])
    with httpx.Client() as http:
        run(ctx_factory(llm, http))
    assert article_id(EKS) not in candidate_ids(llm.parse_calls[0])


def test_second_run_same_day_is_already_posted(httpx_mock, ctx_factory, history_path, now):
    _seed(history_path, _record(EKS, now - timedelta(minutes=30)))  # 07:30 KST today
    llm = FakeAnthropic()
    with httpx.Client() as http:
        result = run(ctx_factory(llm, http))
    assert result.status == RunStatus.ALREADY_POSTED
    assert httpx_mock.get_requests() == []  # no feeds fetched, nothing sent
    assert llm.parse_calls == []


@pytest.mark.parametrize(
    "kw", [{"target": "test", "force": True}, {"dry_run": True, "force": True}]
)
def test_force_bypasses_guard_but_never_writes_history(
    httpx_mock, mock_feeds, ctx_factory, history_path, now, kw
):
    _seed(history_path, _record(EKS, now - timedelta(minutes=30)))
    before = history_path.read_text()
    mock_feeds()
    if kw.get("target") == "test":
        httpx_mock.add_response(url=TEST_HOOK, text="ok")
    llm = FakeAnthropic(responses=[FakeResponse(make_selection(article_id(MCP), "ai_agent"))])
    with httpx.Client() as http:
        result = run(ctx_factory(llm, http, **kw))
    assert result.status == RunStatus.POSTED
    assert history_path.read_text() == before
    assert httpx_mock.get_requests(url=MAIN_HOOK) == []


def test_two_infra_posts_make_ai_agent_preferred(
    httpx_mock, mock_feeds, ctx_factory, history_path, now
):
    _seed(
        history_path,
        _record("https://x.com/1", now - timedelta(days=2), "infra"),
        _record("https://x.com/2", now - timedelta(days=1), "infra"),
    )
    mock_feeds()
    httpx_mock.add_response(url=MAIN_HOOK, text="ok")
    llm = FakeAnthropic(responses=[FakeResponse(make_selection(article_id(AGENTS), "ai_agent"))])
    with httpx.Client() as http:
        run(ctx_factory(llm, http))
    prompt = llm.parse_calls[0]["messages"][0]["content"]
    assert "최근 게시 분류: infra, infra" in prompt
    assert "선호 분류: ai_agent" in prompt


def test_override_without_reason_logs_warning(
    httpx_mock, mock_feeds, ctx_factory, history_path, now, caplog
):
    _seed(
        history_path,
        _record("https://x.com/1", now - timedelta(days=2), "infra"),
        _record("https://x.com/2", now - timedelta(days=1), "infra"),
    )
    mock_feeds()
    httpx_mock.add_response(url=MAIN_HOOK, text="ok")
    llm = FakeAnthropic(responses=[FakeResponse(make_selection(article_id(EKS), "infra"))])
    with caplog.at_level(logging.WARNING), httpx.Client() as http:
        result = run(ctx_factory(llm, http))
    assert result.status == RunStatus.POSTED
    assert any(r.getMessage() == "balance_override_without_reason" for r in caplog.records)


def test_post_failure_does_not_record_history(httpx_mock, mock_feeds, ctx_factory, history_path):
    mock_feeds()
    httpx_mock.add_response(url=MAIN_HOOK, status_code=404, text="no_service")
    httpx_mock.add_response(url=TEST_HOOK, text="ok", is_optional=True)
    llm = FakeAnthropic(responses=[FakeResponse(make_selection(article_id(EKS)))])
    with httpx.Client() as http:
        result = run(ctx_factory(llm, http))
    assert result.status == RunStatus.POST_FAILED
    assert not history_path.exists()
