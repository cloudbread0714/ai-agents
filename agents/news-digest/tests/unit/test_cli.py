import json
import shutil

import pytest
import yaml

from nd_support import CONFIG_DIR, FEED_URLS, MAIN_HOOK, FakeAnthropic, FakeResponse, make_selection
from news_digest import cli
from news_digest.normalize import article_id

EKS = "https://aws.amazon.com/blogs/aws/amazon-eks-kubernetes-1-34/"


@pytest.fixture
def config_dir(tmp_path):
    d = tmp_path / "config"
    d.mkdir()
    shutil.copy(CONFIG_DIR / "settings.yaml", d / "settings.yaml")
    (d / "sources.yaml").write_text(
        yaml.safe_dump(
            {
                "sources": [
                    {
                        "name": "AWS News Blog",
                        "url": FEED_URLS["aws_blog.xml"],
                        "category": "infra",
                    },
                    {"name": "Hacker News", "url": FEED_URLS["hnrss.xml"], "category": "auto"},
                ]
            }
        )
    )
    return d


def _main(argv, environ, llm=None, now=None):
    from nd_support import NOW

    return cli.main(
        argv,
        environ=environ,
        now=now or NOW,
        llm_factory=(lambda settings, api_key: llm) if llm else None,
    )


def test_missing_env_exits_2_and_prints_only_names(config_dir, capsys):
    code = _main(["--config-dir", str(config_dir)], {"ANTHROPIC_API_KEY": "sk-ant-secret"})
    assert code == 2
    err = capsys.readouterr().err
    assert "SLACK_WEBHOOK_URL_MAIN" in err and "SLACK_WEBHOOK_URL_TEST" in err
    assert "sk-ant-secret" not in err


def test_dry_run_needs_only_anthropic_key(config_dir, mock_feeds, capsys):
    mock_feeds()
    llm = FakeAnthropic(responses=[FakeResponse(make_selection(article_id(EKS)))])
    code = _main(["--config-dir", str(config_dir), "--dry-run"], {"ANTHROPIC_API_KEY": "k"}, llm)
    assert code == 0
    out = capsys.readouterr().out.strip().splitlines()
    summary = json.loads(out[-1])
    assert summary["status"] == "POSTED"
    assert summary["selected_id"] == article_id(EKS)


@pytest.mark.parametrize("argv", [["--force"], ["--force", "--target", "main"]])
def test_force_only_with_test_target_or_dry_run(config_dir, env, argv, capsys):
    assert _main(["--config-dir", str(config_dir), *argv], env) == 2
    assert "--force" in capsys.readouterr().err


def test_invalid_config_exits_2(tmp_path, env, capsys):
    (tmp_path / "settings.yaml").write_text("llm: {}\n")
    (tmp_path / "sources.yaml").write_text("sources: []\n")
    assert _main(["--config-dir", str(tmp_path)], env) == 2
    assert "settings.yaml" in capsys.readouterr().err


def test_bad_argument_exits_2(env):
    with pytest.raises(SystemExit) as excinfo:
        _main(["--target", "prod"], env)
    assert excinfo.value.code == 2


def test_startup_error_exits_1(config_dir, env, history_path):
    def broken_factory(settings, api_key):
        raise RuntimeError("cannot build client")

    environ = {**env, "NEWS_DIGEST_HISTORY_PATH": str(history_path)}
    code = cli.main(["--config-dir", str(config_dir)], environ=environ, llm_factory=broken_factory)
    assert code == 1


def test_main_target_posts_to_main(config_dir, env, mock_feeds, httpx_mock, history_path):
    mock_feeds()
    httpx_mock.add_response(url=MAIN_HOOK, text="ok")
    llm = FakeAnthropic(responses=[FakeResponse(make_selection(article_id(EKS)))])
    environ = {**env, "NEWS_DIGEST_HISTORY_PATH": str(history_path)}
    assert _main(["--config-dir", str(config_dir)], environ, llm) == 0
    assert len(httpx_mock.get_requests(url=MAIN_HOOK)) == 1
