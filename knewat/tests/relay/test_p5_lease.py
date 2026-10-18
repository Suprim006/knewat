"""P5-fix Q7: lease_ms is bounded (1 ms .. 24 h): no int64 overflow, no permanent lock."""

from __future__ import annotations

import pytest

from knewat.relay import MAX_LEASE_MS

HUGE = [2**63 - 1, 2**63, 2**62, 10**30, MAX_LEASE_MS + 1]


def _setup(relay):
    relay.register_agent("w", "W", "builder", "test")
    relay.register_agent("x", "X", "builder", "test")
    relay.create_tasks([{"id": "t1", "title": "one"}])


def test_q7_max_lease_is_24_hours():
    assert MAX_LEASE_MS == 24 * 3600 * 1000


@pytest.mark.parametrize("lease", [0, -1, *HUGE])
def test_q7_claim_rejects_out_of_range_lease_and_writes_nothing(relay, lease):
    _setup(relay)
    with pytest.raises(ValueError, match="lease_ms"):
        relay.claim_next_task("w", lease)
    assert relay.task_status("t1")["status"] == "open"


@pytest.mark.parametrize("lease", [0, -1, *HUGE])
def test_q7_heartbeat_rejects_out_of_range_lease(relay, clock, lease):
    _setup(relay)
    relay.claim_next_task("w", 1_000)
    before = relay.task_status("t1")["lease_until"]
    with pytest.raises(ValueError, match="lease_ms"):
        relay.heartbeat("w", "t1", lease)
    assert relay.task_status("t1")["lease_until"] == before


def test_q7_boundary_values_are_accepted(relay, clock):
    _setup(relay)
    assert relay.claim_next_task("w", MAX_LEASE_MS)["lease_until"] == clock.t + MAX_LEASE_MS
    assert relay.heartbeat("w", "t1", 1) is True
