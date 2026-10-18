"""The fault script fires at the steps it is given, and not when it is switched off."""

from __future__ import annotations

import asyncio

from knewat.demo.scenario import FaultScript
from knewat.demo.scripted import run_scripted
from knewat.embed import HashEmbedder

from .conftest import FAST_LEASE_MS, rows


def _run(client, tenant, **kw):
    faults = FaultScript(builder_lease_ms=FAST_LEASE_MS, **kw)
    return asyncio.run(run_scripted(tenant, client, embedder=HashEmbedder(), faults=faults))


def test_later_fault_steps_move_the_faults(client, demo_tenants):
    tenant = demo_tenants()
    w = _run(client, tenant, kill_builder_at=40, publish_v2_at=45)
    # the kill waits until the builder holds a task at/after step 40; v2 comes at the first boundary at/after 45
    assert w.faults.fired["kill_builder"] >= 40 and w.faults.fired["publish_v2"] >= 45
    killed = next(e for e in w.events if e["event"] == "kill_builder")
    assert killed["step"] == w.faults.fired["kill_builder"]
    reclaim = next(e for e in w.events if e["event"] == "reclaim")
    assert reclaim["task"] == killed["task"] and reclaim["reclaimed_from"] == "builder"
    assert rows(client, tenant, "MATCH (t:Task) WHERE t.status <> 'done' RETURN count(t)")[0][0] == 0
    # v2 arrived late, so the early decisions (v1) were made on a fact that was still current when they were made
    assert rows(
        client,
        tenant,
        "MATCH (f:Fact {predicate:'api_version'}) RETURN f.value, f.status ORDER BY f.valid_from",
    ) == [
        ["v1", "superseded"],
        ["v2", "active"],
    ]


def test_no_faults_means_a_straight_run(client, demo_tenants):
    tenant = demo_tenants()
    w = _run(client, tenant, kill_builder_at=None, publish_v2_at=None)
    assert w.faults.fired == {} and [e["event"] for e in w.events] == ["auth_contradiction"]
    assert rows(client, tenant, "MATCH (t:Task) RETURN count(t)")[0][0] == 11  # no v2, so no t12
    assert (
        rows(client, tenant, "MATCH ()-[c:CLAIMED]->() WHERE c.reclaimed_from <> '' RETURN count(c)")[0][0]
        == 0
    )
    assert rows(client, tenant, "MATCH (f:Fact {predicate:'api_version'}) RETURN f.value, f.status") == [
        ["v1", "active"]
    ]


def test_kill_needs_work_after_the_claim(client, demo_tenants):
    tenant = demo_tenants()
    w = _run(client, tenant, kill_builder_at=1, kill_after_calls=2)
    # claimed at 14, recall at 15, then the next call is the 2nd one after the claim -> killed before it
    killed = next(e for e in w.events if e["event"] == "kill_builder")
    assert killed["step"] >= 15
    builder_calls = [c for c in w.calls if c["agent"] == "builder" and c["step"] <= killed["step"]]
    assert [c["tool"] for c in builder_calls[-3:]] == ["claim_next_task", "recall", "remember_episode"]
