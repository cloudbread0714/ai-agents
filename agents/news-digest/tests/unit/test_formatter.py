from datetime import UTC, date, datetime

from nd_support import make_selection
from news_digest.formatter import build_post_payload, escape_mrkdwn
from news_digest.models import Article
from news_digest.normalize import article_id, normalize_url

URL = "https://aws.amazon.com/blogs/aws/amazon-eks-kubernetes-1-34/?utm_source=rss"
ARTICLE = Article(
    id=article_id(URL),
    title="Amazon EKS adds Kubernetes 1.34",
    url=URL,
    normalized_url=normalize_url(URL),
    source="AWS News Blog",
    category_hint="infra",
    published_at=datetime(2026, 10, 25, tzinfo=UTC),
)


def _payload(test_mode=False, **sel):
    selection = make_selection(ARTICLE.id, **sel)
    return build_post_payload(selection, ARTICLE, date(2026, 10, 26), test_mode=test_mode)


def _texts(payload) -> list[str]:
    return [b["text"]["text"] for b in payload["blocks"] if "text" in b]


def test_block_structure():
    payload = _payload(apply_points_ko=["첫째", "둘째"])
    types = [b["type"] for b in payload["blocks"]]
    assert types == ["header", "section", "section", "section", "context"]
    header, content, apply, link = _texts(payload)
    assert header.startswith("📰 EKS, Kubernetes 1.34")
    assert content.startswith("*내용*\n• Amazon EKS가")
    assert content.count("\n• ") == 3
    assert apply == "*나에게 적용할 점*\n1. 첫째\n2. 둘째"
    assert payload["text"] == header
    context = payload["blocks"][-1]["elements"][0]["text"]
    assert context == "분류: infra · 2026-10-26"


def test_link_comes_from_article_not_llm():
    payload = _payload(selection_reason="see https://evil.example")
    link = _texts(payload)[3]
    assert link == f"*원문*  <{URL}|AWS News Blog 원문 보기>"
    assert "evil" not in str(payload)


def test_mrkdwn_escaping():
    assert escape_mrkdwn("a & <b> c") == "a &amp; &lt;b&gt; c"
    payload = _payload(summary_ko=["<!channel> 공지", "x & y", "z"])
    content = _texts(payload)[1]
    assert "&lt;!channel&gt;" in content
    assert "x &amp; y" in content


def test_header_is_plain_text_without_escaping():
    payload = _payload(title_ko="A & B")
    assert payload["blocks"][0]["text"] == {"type": "plain_text", "text": "📰 A & B", "emoji": True}


def test_test_mode_prefix():
    payload = _payload(test_mode=True)
    assert payload["blocks"][0]["text"]["text"].startswith("[TEST] 📰 ")
    assert payload["text"].startswith("[TEST] ")
