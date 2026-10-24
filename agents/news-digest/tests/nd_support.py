"""Test helpers shared by news-digest tests (importable; conftest is not)."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from news_digest.models import DigestSelection

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG_DIR = Path(__file__).parents[1] / "config"

# 2026-10-26 08:00 KST — the scheduled run time.
NOW = datetime(2026, 10, 25, 23, 0, tzinfo=UTC)

MAIN_HOOK = "https://hooks.slack.com/services/T0/B0/MAINMAINMAIN"
TEST_HOOK = "https://hooks.slack.com/services/T0/B0/TESTTESTTEST"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


FEED_URLS = {
    "aws_blog.xml": "https://feeds.test/aws-blog",
    "aws_whats_new.xml": "https://feeds.test/aws-whats-new",
    "hnrss.xml": "https://feeds.test/hn",
    "atom_blog.xml": "https://feeds.test/agents",
}


# --- Fake Anthropic client --------------------------------------------------------------


def make_selection(selected_id: str, category: str = "infra", **overrides) -> DigestSelection:
    data = {
        "selected_id": selected_id,
        "category": category,
        "title_ko": "EKS, Kubernetes 1.34 지원 & 인플레이스 리사이즈",
        "summary_ko": [
            "Amazon EKS가 Kubernetes 1.34를 지원한다.",
            "파드를 재시작하지 않고 리소스를 바꾸는 인플레이스 리사이즈가 포함된다.",
            "노드 자동 복구도 개선됐다.",
        ],
        "apply_points_ko": ["kind 클러스터에서 1.34 인플레이스 리사이즈를 실습해 본다."],
        "selection_reason": "관심 분야(Kubernetes, AWS)와 직접 관련된 주요 기능 변경",
    }
    data.update(overrides)
    return DigestSelection.model_validate(data)


@dataclass
class FakeResponse:
    parsed_output: Any
    stop_reason: str = "end_turn"
    model: str = "claude-opus-5-5"
    input_tokens: int = 10_000
    output_tokens: int = 1_500
    stop_details: Any = None

    @property
    def usage(self):
        return SimpleNamespace(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )


@dataclass
class FakeAnthropic:
    """Records calls; ``responses`` items are FakeResponse, an exception to raise, or a callable
    taking the request kwargs and returning one of those."""

    responses: list[Any] = field(default_factory=list)
    count_tokens_fn: Callable[[dict], int] = lambda kwargs: 10_000
    parse_calls: list[dict] = field(default_factory=list)
    count_calls: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self.messages = _FakeMessages(self, beta=False)
        self.beta = SimpleNamespace(messages=_FakeMessages(self, beta=True))


class _FakeMessages:
    def __init__(self, owner: FakeAnthropic, beta: bool):
        self.owner = owner
        self.beta = beta

    def count_tokens(self, **kwargs):
        self.owner.count_calls.append(kwargs)
        return SimpleNamespace(input_tokens=self.owner.count_tokens_fn(kwargs))

    def parse(self, **kwargs):
        self.owner.parse_calls.append({**kwargs, "_beta": self.beta})
        if not self.owner.responses:
            raise AssertionError("FakeAnthropic: no more responses queued")
        item = self.owner.responses.pop(0)
        if callable(item) and not isinstance(item, FakeResponse):
            item = item(kwargs)
        if isinstance(item, BaseException):
            raise item
        return item


def candidate_ids(kwargs: dict) -> list[str]:
    return re.findall(r'<candidate id="([0-9a-f]{16})"', kwargs["messages"][0]["content"])
