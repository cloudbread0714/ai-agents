"""``config/job.yaml`` and the agent's paths (research R11)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from job_apply.errors import EnvNotReady
from shared.config import MissingEnvError, load_yaml, require_env

AGENT_ROOT = Path(__file__).resolve().parents[2]
TOKEN_ENV = "SLACK_BOT_TOKEN"
CHANNEL_ENV = "SLACK_JOB_CHANNEL_ID"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SlackConfig(_Strict):
    channel_id: str = ""


class FetchConfig(_Strict):
    timeout_s: float = 15
    min_chars: int = 400
    user_agent: str = "Mozilla/5.0"


class RenderConfig(_Strict):
    timeout_s: float = 120
    max_attempts: int = 3
    overflow_tolerance_pt: float = 4
    preview_dpi: int = 150
    # Font name in the originals → installed font LibreOffice draws instead (e.g. a Windows
    # font such as 맑은 고딕 on macOS). Without a pair, LibreOffice picks its own fallback.
    font_substitutes: dict[str, str] = Field(default_factory=dict)


class JobConfig(_Strict):
    slack: SlackConfig = Field(default_factory=SlackConfig)
    fetch: FetchConfig = Field(default_factory=FetchConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def private(self) -> Path:
        return self.root / "private"

    @property
    def resume(self) -> Path:
        return self.private / "resume.docx"

    @property
    def portfolio(self) -> Path:
        return self.private / "portfolio.pptx"

    @property
    def applications(self) -> Path:
        return self.root / "applications"

    @property
    def state(self) -> Path:
        return self.root / ".job-state"

    @property
    def inbox(self) -> Path:
        return self.state / "inbox"

    @property
    def logs(self) -> Path:
        return self.state / "logs"

    @property
    def lo_profile(self) -> Path:
        return self.state / "lo-profile"

    @property
    def config_file(self) -> Path:
        return self.root / "config" / "job.yaml"

    def rel(self, path: Path) -> str:
        """Path as shown to the user: relative to the repo root (agents/job-apply/...)."""
        try:
            return str(path.relative_to(self.root.parents[1]))
        except ValueError:
            return str(path)


def load_config(paths: Paths) -> JobConfig:
    return load_yaml(paths.config_file, JobConfig)


def slack_token(environ: Mapping[str, str]) -> str:
    try:
        return require_env(TOKEN_ENV, environ=environ)[TOKEN_ENV]
    except MissingEnvError as exc:
        raise EnvNotReady(f"환경변수가 없어요: {', '.join(exc.names)}") from None


def slack_channel(cfg: JobConfig, environ: Mapping[str, str]) -> str:
    channel = environ.get(CHANNEL_ENV) or cfg.slack.channel_id
    if not channel:
        raise EnvNotReady("Slack 채널이 설정되지 않았어요(config/job.yaml slack.channel_id)")
    return channel
