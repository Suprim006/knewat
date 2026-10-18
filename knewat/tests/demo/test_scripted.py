"""The scripted Acme Notes run, end to end on a throwaway tenant, checked against the graph it leaves."""

from __future__ import annotations

import asyncio

from plexus.demo.inventory import inventory
from plexus.demo.scenario import FaultScript, load_scenario
from plexus.demo.scripted import run_scripted
from plexus.embed import HashEmbedder
from plexus.graph.tenancy import graph_name
from plexus.lineage import Lineage

from .conftest import FAST_LEASE_MS, rows


def test_scenario_data_is_complete():
    sc = load_scenario()
    assert len(sc.sources) == 7  # 6 documents of the story + the unverified forum post (stretch)
    assert len(sc.all_tasks) == 12
    ids = {t.id for t in sc.all_tasks}
    assert all(d in ids for t in sc.all_tasks for d in t.depends_on)
    assert {t.role for t in sc.all_tasks} == {"planner", "researcher", "builder"}


def test_all_tasks_done_and_every_call_has_a_toolcall(client, scripted_run):
    tenant, w = scripted_run
    assert [r[0] for r in rows(client, tenant, "MATCH (t:Task) WHERE t.status <> 'done' RETURN t.id")] == []
    assert rows(client, tenant, "MATCH (t:Task) RETURN count(t)")[0][0] == 12
    assert rows(client, tenant, "MATCH (c:ToolCall) RETURN count(c)")[0][0] == w.step == len(w.calls)
    # every call is attributable to a Step of the calling agent, with the global step number
    assert (
        rows(client, tenant, "MATCH (c:ToolCall) WHERE NOT (c)-[:IN_STEP]->(:Step) RETURN count(c)")[0][0]
        == 0
    )
    got = {
        (r[0], r[1])
        for r in rows(client, tenant, "MATCH (c:ToolCall)-[:IN_STEP]->(s:Step) RETURN c.agent_id, s.n")
    }
    assert got == {(c["agent"], c["step"]) for c in w.calls}


def test_version_v1_is_superseded_by_v2(client, scripted_run):
    tenant, _ = scripted_run
    r = rows(
        client,
        tenant,
        "MATCH (new:Fact {predicate:'api_version'})-[:SUPERSEDES]->(old:Fact) "
        "RETURN old.value, old.status, new.value, new.status, old.valid_to = new.valid_from",
    )
    assert r == [["v1", "superseded", "v2", "active", True]]


def test_conflicting_auth_assertions_from_two_agents(client, scripted_run):
    tenant, _ = scripted_run
    r = rows(
        client,
        tenant,
        "MATCH (a:Fact)-[:CONTRADICTS]->(b:Fact) "
        "MATCH (a)-[:ASSERTED_BY]->(x:Agent) MATCH (b)-[:ASSERTED_BY]->(y:Agent) "
        "RETURN a.predicate, a.value, x.id, a.status, b.value, y.id, b.status",
    )
    assert r == [
        [
            "auth_method",
            "API key in X-Api-Key header",
            "planner",
            "active",
            "JWT bearer tokens (RS256)",
            "researcher",
            "active",
        ]
    ]


def test_builder_killed_and_task_reclaimed(client, scripted_run):
    tenant, w = scripted_run
    claims = rows(
        client,
        tenant,
        "MATCH (a:Agent)-[c:CLAIMED]->(t:Task {id:'t03-design-endpoints'}) "
        "RETURN a.id, c.reclaimed_from ORDER BY c.at",
    )
    assert claims == [["builder", ""], ["researcher", "builder"]]
    t03 = rows(client, tenant, "MATCH (t:Task {id:'t03-design-endpoints'}) RETURN t.status, t.claimed_by")[0]
    assert t03 == ["done", "researcher"]
    # the builder came back (a second session) and later work was done by it
    assert (
        rows(client, tenant, "MATCH (:Agent {id:'builder'})-[:HAD]->(s:Session) RETURN count(s)")[0][0] == 2
    )
    assert (
        rows(client, tenant, "MATCH (:Agent {id:'builder'})-[:CLAIMED]->(t:Task) RETURN count(t)")[0][0] == 5
    )  # t03 (killed), t12, t06, t07, t11
    ev = {e["event"]: e for e in w.events}
    assert ev["kill_builder"]["task"] == "t03-design-endpoints"
    assert ev["reclaim"]["agent"] == "researcher" and ev["reclaim"]["reclaimed_from"] == "builder"


def test_decisions_are_based_on_facts(client, scripted_run):
    tenant, _ = scripted_run
    r = rows(
        client,
        tenant,
        "MATCH (d:Decision) OPTIONAL MATCH (d)-[:BASED_ON]->(f:Fact) "
        "RETURN d.text, collect(f.value) ORDER BY d.created_at",
    )
    assert len(r) == 4
    assert all(basis for _, basis in r)
    # the v1 decision rests on the superseded fact, the v2 decision on the active one
    assert r[0][1] == ["v1"] and any(basis == ["v2"] for _, basis in r)
    assert any(
        sorted(basis) == ["API key in X-Api-Key header", "JWT bearer tokens (RS256)"] for _, basis in r
    )


def test_facts_trace_to_sources(client, scripted_run):
    tenant, _ = scripted_run
    r = rows(client, tenant, "MATCH (f:Fact)-[:DERIVED_FROM]->(s:Source) RETURN count(DISTINCT s), count(f)")[
        0
    ]
    assert r == [6, 6]  # six documents, one fact each (purpose, v1, v2, database, jwt, API key)
    assert rows(client, tenant, "MATCH (s:Source) RETURN count(s)")[0][0] == 6


def test_fault_script_fires_at_the_scripted_steps(scripted_run):
    _, w = scripted_run
    assert w.faults.fired == {"kill_builder": 15, "publish_v2": 20}
    builder_steps = [c["step"] for c in w.calls if c["agent"] == "builder"]
    assert 15 in builder_steps and 16 not in builder_steps[:3]  # killed right after its step 15
    first_after = next(c for c in w.calls if c["step"] == 16)
    assert first_after["agent"] == "researcher" and first_after["tool"] == "claim_next_task"
    ingest = next(c for c in w.calls if c["step"] == 21)
    assert ingest["agent"] == "researcher" and ingest["tool"] == "add_source"


def test_time_machine_builder_knew_v1_then_v2(client, scripted_run):
    tenant, w = scripted_run
    lin = Lineage(client, graph_name(tenant))

    def versions(step: int) -> set[str]:
        return {f["value"] for f in lin.knew_at("builder", step)["facts"] if f["predicate"] == "api_version"}

    assert versions(15) == {"v1"}  # read just before it was killed
    assert versions(w.step) == {"v2"}  # after the restart: the v1 it read earlier is no longer valid


def test_inventory_counts(client, scripted_run):
    tenant, _ = scripted_run
    inv = inventory(client, tenant)
    assert inv["nodes"]["Task"] == 12 and inv["nodes"]["Decision"] == 4 and inv["nodes"]["Source"] == 6
    assert inv["nodes"]["ToolCall"] == 67
    assert inv["edges"]["CONTRADICTS"] == 1 and inv["edges"]["SUPERSEDES"] == 1


def test_same_seed_gives_the_same_graph(client, demo_tenants, scripted_run):
    tenant, w = scripted_run
    t2 = demo_tenants()
    w2 = asyncio.run(
        run_scripted(t2, client, embedder=HashEmbedder(), faults=FaultScript(builder_lease_ms=FAST_LEASE_MS))
    )
    assert [(c["step"], c["agent"], c["tool"]) for c in w.calls] == [
        (c["step"], c["agent"], c["tool"]) for c in w2.calls
    ]
    assert inventory(client, tenant) == inventory(client, t2)
    q = "MATCH (f:Fact) RETURN f.predicate, f.value, f.status ORDER BY f.predicate, f.value"
    assert rows(client, tenant, q) == rows(client, t2, q)


def test_poison_variant_quarantines_the_forum_post(client, demo_tenants):
    tenant = demo_tenants()
    w = asyncio.run(
        run_scripted(
            tenant,
            client,
            embedder=HashEmbedder(),
            faults=FaultScript(builder_lease_ms=FAST_LEASE_MS, poison_at=40),
        )
    )
    assert "poison" in w.faults.fired
    r = rows(client, tenant, "MATCH (f:Fact {value:'MongoDB 4'}) RETURN f.status")
    assert r == [["quarantined"]]
    assert rows(client, tenant, "MATCH (f:Fact {value:'PostgreSQL 16'}) RETURN f.status") == [["active"]]
    q = [e for e in w.events if e["event"] == "quarantine"][0]
    assert q["blast_radius"]["decision_ids"]  # the decision built on the poisoned fact is in the blast radius
