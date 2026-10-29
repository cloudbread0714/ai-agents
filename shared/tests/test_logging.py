import json
import logging

import pytest

from shared.logging import JsonFormatter, SecretMaskingFilter, mask_secrets


@pytest.mark.parametrize(
    ("raw", "masked"),
    [
        ("token xoxb-1234-5678-abcDEF here", "token xoxb-*** here"),
        ("user xoxp-1-2-3", "user xoxp-***"),
        ("Bearer xoxa-2-abc", "Bearer xoxa-***"),
        ("refresh xoxr-zzz", "refresh xoxr-***"),
        ("sk-ant-api03-abc_def", "sk-ant-***"),
        ("https://hooks.slack.com/services/T0/B0/SECRET", "https://hooks.slack.com/services/***"),
        ("no secrets", "no secrets"),
    ],
)
def test_mask_secrets(raw, masked):
    assert mask_secrets(raw) == masked


def test_filter_masks_message_and_fields():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "auth %s", ("xoxb-1-2-3",), None)
    record.fields = {"header": "Bearer xoxb-9-9", "nested": ["xoxp-1"]}
    SecretMaskingFilter().filter(record)
    line = JsonFormatter().format(record)
    assert "xoxb-1" not in line and "xoxb-9" not in line and "xoxp-1" not in line
    assert json.loads(line)["event"] == "auth xoxb-***"
