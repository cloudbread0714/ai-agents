"""Structured JSON logging to stderr with secret masking.

Callers attach structured data through ``extra={"fields": {...}}``; the formatter
emits one JSON object per line.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

_SECRET_PATTERNS = [
    (re.compile(r"(https://hooks\.slack\.com/services/)\S+"), r"\1***"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]+"), "sk-ant-***"),
    (re.compile(r"\b(xox[abpr])-[A-Za-z0-9-]+"), r"\1-***"),
]


def mask_secrets(text: str) -> str:
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _mask_value(value: Any) -> Any:
    if isinstance(value, str):
        return mask_secrets(value)
    if isinstance(value, dict):
        return {k: _mask_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_mask_value(v) for v in value]
    return value


class SecretMaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_secrets(record.getMessage())
        record.args = None
        fields = getattr(record, "fields", None)
        if fields is not None:
            record.fields = _mask_value(fields)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "fields", None) or {})
        if record.exc_info:
            payload["exc"] = mask_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(f, SecretMaskingFilter) for f in logger.filters):
        logger.addFilter(SecretMaskingFilter())
    return logger


def configure(level: int = logging.INFO) -> None:
    """Send all logs to stderr as JSON lines. Call once from a CLI entry point."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretMaskingFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for noisy in ("httpx", "httpcore", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
