from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from nd_support import CONFIG_DIR, FEED_URLS, MAIN_HOOK, NOW, TEST_HOOK, fixture_bytes
from news_digest.models import BudgetSettings, LLMSettings, Settings, SourcesFile
from shared.config import load_yaml


@pytest.fixture
def now() -> datetime:
    return NOW


@pytest.fixture
def settings() -> Settings:
    # Pin the LLM/budget values the tests assert on, so changing the model in
    # config/settings.yaml doesn't break them.
    loaded = load_yaml(CONFIG_DIR / "settings.yaml", Settings)
    return loaded.model_copy(
        update={
            "llm": LLMSettings(model="claude-opus-5-5", max_tokens=4000, fallbacks="default"),
            "budget": BudgetSettings(max_cost_usd_per_run=0.30),
        }
    )


@pytest.fixture
def env() -> dict[str, str]:
    return {
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "SLACK_WEBHOOK_URL_MAIN": MAIN_HOOK,
        "SLACK_WEBHOOK_URL_TEST": TEST_HOOK,
    }


@pytest.fixture
def history_path(tmp_path) -> Path:
    return tmp_path / "posted.json"


@pytest.fixture
def sources() -> SourcesFile:
    return SourcesFile.model_validate(
        {
            "sources": [
                {"name": "AWS News Blog", "url": FEED_URLS["aws_blog.xml"], "category": "infra"},
                {
                    "name": "AWS What's New",
                    "url": FEED_URLS["aws_whats_new.xml"],
                    "category": "infra",
                },
                {"name": "Hacker News", "url": FEED_URLS["hnrss.xml"], "category": "auto"},
                {"name": "Agents Blog", "url": FEED_URLS["atom_blog.xml"], "category": "ai_agent"},
            ]
        }
    )


@pytest.fixture
def mock_feeds(httpx_mock):
    """Serve every fixture feed; ``overrides`` maps a fixture name to an exception or
    response kwargs to replace it."""

    def serve(overrides: dict[str, Any] | None = None) -> None:
        overrides = overrides or {}
        for fixture, url in FEED_URLS.items():
            override = overrides.get(fixture)
            if override is None:
                httpx_mock.add_response(
                    url=url, content=fixture_bytes(fixture), is_reusable=True, is_optional=True
                )
            elif isinstance(override, Exception):
                httpx_mock.add_exception(override, url=url, is_reusable=True, is_optional=True)
            else:
                httpx_mock.add_response(url=url, is_reusable=True, is_optional=True, **override)

    return serve
