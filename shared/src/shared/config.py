"""YAML config loading with Pydantic validation, and environment variable helpers.

Secrets come only from the environment (constitution IV), so config files that
contain secret-looking keys are rejected.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

_SECRET_KEY_RE = re.compile(r"((^|_)key$|webhook|(^|_)secret$|(^|_)password$|(^|_)token$)", re.I)


class ConfigError(Exception):
    pass


class MissingEnvError(ConfigError):
    def __init__(self, names: list[str]):
        self.names = names
        super().__init__(f"missing environment variables: {', '.join(names)}")


def _secret_keys(node: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            key_path = f"{path}.{key}" if path else str(key)
            if _SECRET_KEY_RE.search(str(key)):
                found.append(key_path)
            found.extend(_secret_keys(value, key_path))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            found.extend(_secret_keys(item, f"{path}[{i}]"))
    return found


def load_yaml[T: BaseModel](path: Path | str, model: type[T]) -> T:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"{path}: config file not found")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from None
    if secret_keys := _secret_keys(data):
        raise ConfigError(
            f"{path}: secret-looking keys are not allowed in config files "
            f"(use environment variables): {', '.join(secret_keys)}"
        )
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{path}: {exc}") from None


def require_env(*names: str, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return the named variables, or raise listing only the names that are missing or empty."""
    env = os.environ if environ is None else environ
    missing = [name for name in names if not env.get(name)]
    if missing:
        raise MissingEnvError(missing)
    return {name: env[name] for name in names}
