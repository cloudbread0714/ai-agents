"""``news-digest`` command line entry point (contracts/cli.md)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from news_digest.models import RunResult, RunStatus, Settings, SourcesFile
from news_digest.pipeline import RunContext, run
from shared import logging as shared_logging
from shared.config import ConfigError, MissingEnvError, load_yaml, require_env
from shared.llm import make_client
from shared.logging import get_logger

log = get_logger(__name__)

AGENT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR = AGENT_DIR / "config"
DEFAULT_HISTORY_PATH = AGENT_DIR / "data" / "posted.json"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

_OK_STATUSES = {RunStatus.POSTED, RunStatus.ALREADY_POSTED, RunStatus.NO_NEW_ARTICLES}

LLMFactory = Callable[[Settings, str], Any]


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="news-digest", description="Post today's most important tech article to Slack."
    )
    p.add_argument("--target", choices=["main", "test"], default="main")
    p.add_argument("--dry-run", action="store_true", help="print the post; send nothing to Slack")
    p.add_argument(
        "--force",
        action="store_true",
        help="ignore the once-per-day guard (only with --target test or --dry-run)",
    )
    p.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
    return p


def exit_code(result: RunResult) -> int:
    return EXIT_OK if result.status in _OK_STATUSES else EXIT_FAILED


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
    llm_factory: LLMFactory | None = None,
) -> int:
    shared_logging.configure()
    environ = os.environ if environ is None else environ
    args = _parser().parse_args(argv)

    if args.force and not (args.target == "test" or args.dry_run):
        print("error: --force requires --target test or --dry-run", file=sys.stderr)
        return EXIT_USAGE

    try:
        settings = load_yaml(args.config_dir / "settings.yaml", Settings)
        sources = load_yaml(args.config_dir / "sources.yaml", SourcesFile)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    required = ["ANTHROPIC_API_KEY"]
    if not args.dry_run:
        required.append("SLACK_WEBHOOK_URL_TEST")
        if args.target == "main":
            required.append("SLACK_WEBHOOK_URL_MAIN")
    try:
        env = require_env(*required, environ=environ)
    except MissingEnvError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    factory = llm_factory or (
        lambda s, key: make_client(max_retries=s.llm.max_retries, api_key=key)
    )
    history_path = Path(environ.get("NEWS_DIGEST_HISTORY_PATH") or DEFAULT_HISTORY_PATH)

    # run() alerts on its own failures; this only catches errors before it can start.
    try:
        llm = factory(settings, env["ANTHROPIC_API_KEY"])
        with httpx.Client() as http:
            result = run(
                RunContext(
                    settings=settings,
                    sources=sources,
                    env={**env, **{k: v for k, v in environ.items() if k.startswith("GITHUB_")}},
                    http=http,
                    llm=llm,
                    now=now or datetime.now(UTC),
                    history_path=history_path,
                    target=args.target,
                    dry_run=args.dry_run,
                    force=args.force,
                )
            )
    except Exception:  # noqa: BLE001
        log.exception("startup_failed")
        return EXIT_FAILED

    print(json.dumps(result.summary(), ensure_ascii=False, default=str))
    return exit_code(result)


if __name__ == "__main__":
    sys.exit(main())
