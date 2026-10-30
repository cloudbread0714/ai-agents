import pytest

from job_apply.config import JobConfig, Paths, load_config, slack_channel, slack_token
from job_apply.errors import EnvNotReady
from shared.config import ConfigError, load_yaml


def test_real_config_loads():
    from job_apply.config import AGENT_ROOT

    cfg = load_config(Paths(AGENT_ROOT))
    assert cfg.render.max_attempts == 3 and cfg.fetch.min_chars == 400
    assert cfg.render.font_substitutes["맑은 고딕"]


def test_secret_looking_keys_are_rejected(tmp_path):
    path = tmp_path / "job.yaml"
    path.write_text("slack:\n  token: xoxb-1\n")
    with pytest.raises(ConfigError, match="slack.token"):
        load_yaml(path, JobConfig)


def test_token_only_from_environment():
    assert slack_token({"SLACK_BOT_TOKEN": "x"}) == "x"
    with pytest.raises(EnvNotReady, match="SLACK_BOT_TOKEN"):
        slack_token({})


def test_channel_from_env_or_config():
    cfg = JobConfig.model_validate({"slack": {"channel_id": "C0CFG"}})
    assert slack_channel(cfg, {}) == "C0CFG"
    assert slack_channel(cfg, {"SLACK_JOB_CHANNEL_ID": "C0ENV"}) == "C0ENV"
    with pytest.raises(EnvNotReady):
        slack_channel(JobConfig(), {})
