"""P12: apply_schema retries FalkorDB's transient "another write is in progress" (concurrent schema build)."""

from __future__ import annotations

import time

import pytest
from redis.exceptions import ResponseError

from knewat.graph.schema import _retry_busy


def test_busy_is_retried_until_it_succeeds():
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise ResponseError("another write is in progress, retry the query")
        return "ok"

    assert _retry_busy(fn, time.monotonic() + 5, poll_s=0) == "ok" and len(calls) == 3


def test_other_errors_and_the_deadline_raise():
    def other():
        raise ResponseError("Attribute 'id' is already indexed")

    with pytest.raises(ResponseError, match="already indexed"):
        _retry_busy(other, time.monotonic() + 5, poll_s=0)

    def busy():
        raise ResponseError("another write is in progress, retry the query")

    with pytest.raises(ResponseError, match="in progress"):
        _retry_busy(busy, time.monotonic() - 1, poll_s=0)
