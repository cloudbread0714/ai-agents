import pytest
from pydantic import BaseModel

from shared.config import ConfigError, MissingEnvError, load_yaml, require_env


class Sample(BaseModel):
    name: str
    max_tokens: int = 10


def test_load_yaml_validates(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text("name: demo\nmax_tokens: 5\n")
    assert load_yaml(path, Sample) == Sample(name="demo", max_tokens=5)


def test_load_yaml_schema_error_names_file(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text("max_tokens: nope\n")
    with pytest.raises(ConfigError, match="s.yaml"):
        load_yaml(path, Sample)


def test_load_yaml_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_yaml(tmp_path / "missing.yaml", Sample)


@pytest.mark.parametrize(
    "body",
    [
        "name: x\napi_key: abc\n",
        "name: x\nnested:\n  slack_webhook: https://example.com\n",
        "name: x\nWebhookUrl: y\n",
    ],
)
def test_load_yaml_rejects_secret_keys(tmp_path, body):
    path = tmp_path / "s.yaml"
    path.write_text(body)
    with pytest.raises(ConfigError, match="secret"):
        load_yaml(path, Sample)


def test_require_env_returns_values():
    assert require_env("A", "B", environ={"A": "1", "B": "2"}) == {"A": "1", "B": "2"}


def test_require_env_reports_only_names():
    with pytest.raises(MissingEnvError) as excinfo:
        require_env("A", "B", "C", environ={"A": "secret-value", "C": ""})
    assert excinfo.value.names == ["B", "C"]
    assert "secret-value" not in str(excinfo.value)
