from pathlib import Path

import pytest
import yaml

from news_digest.models import Settings, SourcesFile
from shared.config import ConfigError, load_yaml

CONFIG_DIR = Path(__file__).parents[2] / "config"


def test_shipped_config_files_are_valid():
    settings = load_yaml(CONFIG_DIR / "settings.yaml", Settings)
    sources = load_yaml(CONFIG_DIR / "sources.yaml", SourcesFile)
    assert settings.llm.model in settings.pricing
    assert len(sources.enabled) >= 1


def _settings(**overrides) -> dict:
    data = yaml.safe_load((CONFIG_DIR / "settings.yaml").read_text())
    for dotted, value in overrides.items():
        node = data
        *parents, leaf = dotted.split(".")
        for key in parents:
            node = node[key]
        node[leaf] = value
    return data


@pytest.mark.parametrize(
    "overrides",
    [
        {"llm.model": "claude-not-priced"},
        {"budget.max_cost_usd_per_run": 0},
        {"selection.freshness_hours": 12},
    ],
)
def test_invalid_settings_rejected(overrides):
    with pytest.raises(ValueError):
        Settings.model_validate(_settings(**overrides))


@pytest.mark.parametrize(
    "sources",
    [
        [
            {"name": "A", "url": "https://a.example/feed", "category": "infra"},
            {"name": "A", "url": "https://b.example/feed", "category": "infra"},
        ],
        [{"name": "A", "url": "ftp://a.example/feed", "category": "infra"}],
        [{"name": "A", "url": "https://a.example/feed", "category": "infra", "enabled": False}],
        [{"name": "A", "url": "https://a.example/feed", "category": "security"}],
    ],
)
def test_invalid_sources_rejected(sources):
    with pytest.raises(ValueError):
        SourcesFile.model_validate({"sources": sources})


def test_secret_in_settings_rejected(tmp_path):
    data = _settings()
    data["slack_webhook"] = "https://hooks.slack.com/services/x"
    path = tmp_path / "settings.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True))
    with pytest.raises(ConfigError, match="secret"):
        load_yaml(path, Settings)
