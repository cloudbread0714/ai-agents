"""Slack Block Kit payload for the daily post (contracts/slack-message.md)."""

from __future__ import annotations

from datetime import date
from typing import Any

from news_digest.models import Article, DigestSelection


def escape_mrkdwn(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _link(url: str, label: str) -> str:
    safe_url = url.replace("|", "%7C").replace(">", "%3E").replace("<", "%3C")
    return f"<{safe_url}|{escape_mrkdwn(label)}>"


def _section(text: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def build_post_payload(
    selection: DigestSelection, article: Article, date_kst: date, *, test_mode: bool = False
) -> dict[str, Any]:
    """The link always comes from the collected ``article``, never from model output."""
    title = f"{'[TEST] ' if test_mode else ''}📰 {selection.title_ko}"
    summary = "\n".join(f"• {escape_mrkdwn(line)}" for line in selection.summary_ko)
    points = "\n".join(
        f"{i}. {escape_mrkdwn(point)}" for i, point in enumerate(selection.apply_points_ko, 1)
    )
    return {
        "text": title,
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": title, "emoji": True}},
            _section(f"*내용*\n{summary}"),
            _section(f"*나에게 적용할 점*\n{points}"),
            _section(f"*원문*  {_link(article.url, f'{article.source} 원문 보기')}"),
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"분류: {selection.category} · {date_kst.isoformat()}",
                    }
                ],
            },
        ],
    }
