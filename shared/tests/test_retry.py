import logging

import pytest

from shared.retry import retryable


class Flaky(Exception):
    pass


def test_returns_after_transient_failures():
    calls = []

    @retryable(retry_on=(Flaky,), max_attempts=3, base_delay=0, target="unit")
    def op():
        calls.append(1)
        if len(calls) < 3:
            raise Flaky("boom")
        return "done"

    assert op() == "done"
    assert len(calls) == 3


def test_reraises_last_error_when_attempts_exhausted():
    calls = []

    @retryable(retry_on=(Flaky,), max_attempts=3, base_delay=0, target="unit")
    def op():
        calls.append(1)
        raise Flaky(f"fail {len(calls)}")

    with pytest.raises(Flaky, match="fail 3"):
        op()
    assert len(calls) == 3


def test_does_not_retry_other_errors():
    calls = []

    @retryable(retry_on=(Flaky,), max_attempts=3, base_delay=0, target="unit")
    def op():
        calls.append(1)
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        op()
    assert len(calls) == 1


def test_logs_each_retry_with_target_and_attempt(caplog):
    @retryable(retry_on=(Flaky,), max_attempts=3, base_delay=0, target="feed:aws")
    def op():
        raise Flaky("boom")

    with caplog.at_level(logging.WARNING), pytest.raises(Flaky):
        op()

    retries = [r for r in caplog.records if r.getMessage() == "retry"]
    assert [r.fields["attempt"] for r in retries] == [1, 2]
    assert all(r.fields["target"] == "feed:aws" for r in retries)
    assert all(r.fields["error"] == "Flaky: boom" for r in retries)
