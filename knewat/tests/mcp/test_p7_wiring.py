"""P7-int slice 2: staleness (J) and activation forgetting (K) wired together, through the real MCP tools."""

from __future__ import annotations

import asyncio
import time

from mcp import Client
from plexus.activation import Activation
from plexus.graph.tenancy import graph_name

from .test_tool_coverage import ok, rows

REPO_DOC = "C:/repo/docs/payments.md"
CODE = "C:/repo/app/payments.py"
SCOPE = "project:acme"


def now_ms() -> int:
    return time.time_ns() // 1_000_000


async def _decided_fact(c: Client, predicate: str, value: str, decide: bool = False, source_id=None) -> str:
    f = await ok(
        c,
        "assert_fact",
        agent_id="alice",
        subject="Payments",
        predicate=predicate,
        value=value,
        scope="project:acme",
        source_id=source_id,
    )
    if decide:
        await ok(c, "register_agent", agent_id="alice")
        await ok(c, "create_tasks", agent_id="alice", tasks=[{"id": f"t-{predicate}", "title": "t"}])
        await ok(
            c,
            "record_decision",
            agent_id="alice",
            task_id=f"t-{predicate}",
            text=f"rely on {predicate}",
            based_on_fact_ids=[f["fact_id"]],
        )
    return f["fact_id"]


async def _anchor(c: Client, fact_id: str, path: str = CODE) -> None:
    await ok(c, "anchor_fact", agent_id="alice", fact_id=fact_id, path=path, hash="h0")


async def test_end_to_end_repo_source_to_changed_value(server, client, tenant):
    """Facts from a repo-uri Source -> mark_changed -> recall: suspect + reason -> verify_fact (changed) ->
    as_of before / after -> why shows the change."""
    async with Client(server) as c:
        src = (await ok(c, "add_source", agent_id="alice", title="Payments doc", uri=REPO_DOC, kind="doc"))[
            "source_id"
        ]
        fid = await _decided_fact(c, "timeout", "30 seconds", decide=True, source_id=src)
        t_before = now_ms()
        await asyncio.sleep(0.05)
        t_change = now_ms()
        base = await ok(c, "mark_changed", agent_id="hook", changes=[{"path": REPO_DOC, "new_hash": "h0"}])
        assert base["change_id"] is None  # first sighting is a baseline
        out = await ok(
            c,
            "mark_changed",
            agent_id="hook",
            changes=[{"path": REPO_DOC, "new_hash": "h1"}],
            commit="abc123",
            at=t_change,
        )
        assert out["suspect_fact_ids"] == [fid], "implicit anchoring through the Source uri"

        r = await ok(
            c, "recall", agent_id="bob", query="payments timeout", scope="project:acme", detail="full"
        )
        row = next(x for x in r["facts"] if x["fact_id"] == fid)  # still returned, never dropped
        assert row["verify_state"] == "suspect" and row["suspect_since"] == t_change
        assert row["suspect_reason"] == f"changed in abc123 ({REPO_DOC})"
        assert isinstance(row["activation"], float) and row["protected"] is True  # a decision rests on it
        # the compact default (P12) keeps every non-default flag: the suspect warning is never trimmed
        r = await ok(c, "recall", agent_id="bob", query="payments timeout", scope="project:acme")
        row = next(x for x in r["facts"] if x["fact_id"] == fid)
        assert row["verify_state"] == "suspect" and row["suspect_since"] == t_change
        assert row["suspect_reason"] == f"changed in abc123 ({REPO_DOC})" and row["protected"] is True
        assert "path" not in row and "text" not in row and "activation" not in row

        v = await ok(
            c, "verify_fact", agent_id="bob", fact_id=fid, still_true=False, new_value="60 seconds",
            evidence=REPO_DOC, commit="abc123",
        )  # fmt: skip
        assert v["outcome"] == "changed" and v["valid_to"] == t_change

        old = (
            await ok(
                c, "as_of", agent_id="bob", subject="Payments", predicate="timeout", scope=SCOPE, t=t_before
            )
        )["as_of"]
        new = (
            await ok(
                c, "as_of", agent_id="bob", subject="Payments", predicate="timeout", scope=SCOPE, t=now_ms()
            )
        )["as_of"]
        assert old["value"] == "30 seconds" and new["value"] == "60 seconds"
        edge = (
            await ok(
                c,
                "as_of",
                agent_id="bob",
                subject="Payments",
                predicate="timeout",
                scope=SCOPE,
                t=t_change - 1,
            )
        )["as_of"]
        assert edge["value"] == "30 seconds"  # the change is backdated to when the code changed

        w = (await ok(c, "why", agent_id="bob", node_id=fid))["why"]
        kinds = {n["label"] for n in w["nodes"]}
        assert "Change" in kinds, "why shows the change that made the fact suspect"
        rels = {(e["rel"], e["from"] == fid) for e in w["edges"]}
        assert ("VERIFIED_BY", True) in rels
        (fact,) = w["facts"]
        assert len(fact["suspected_by"]) == 1 and fact["verified_by"] == ["bob"]
        change = next(n for n in w["nodes"] if n["label"] == "Change")
        assert change["props"]["commit"] == "abc123"


async def test_why_decision_includes_the_changes_and_verifications_it_rests_on(server, client, tenant):
    async with Client(server) as c:
        fid = await _decided_fact(c, "timeout", "30 seconds", decide=True)
        decision = rows(client, tenant, "MATCH (d:Decision) RETURN d.id")[0][0]
        await _anchor(c, fid)
        await ok(c, "mark_changed", agent_id="hook", changes=[{"path": CODE, "new_hash": "h1"}], commit="c1")
        w = (await ok(c, "why", agent_id="bob", node_id=decision))["why"]
        (fact,) = w["facts"]
        assert fact["id"] == fid and len(fact["suspected_by"]) == 1 and fact["verified_by"] == []
        assert any(e["rel"] == "SUSPECTED" and e["to"] == fid for e in w["edges"])
        await ok(c, "verify_fact", agent_id="bob", fact_id=fid, still_true=True)
        w = (await ok(c, "why", agent_id="bob", node_id=decision))["why"]
        assert w["facts"][0]["verified_by"] == ["bob"]
        assert any(e["rel"] == "VERIFIED_BY" and e["from"] == fid for e in w["edges"])
        # the Change node is a leaf of the explanation: its other touched nodes do not drag in the graph
        assert all(n["label"] != "CodeAnchor" for n in w["nodes"])


async def test_facts_to_verify_orders_by_decisions_then_activation_then_age(server, client, tenant):
    async with Client(server) as c:
        used = await _decided_fact(c, "a_used", "1")
        idle = await _decided_fact(c, "b_idle", "2")
        decided = await _decided_fact(c, "c_decided", "3", decide=True)
        tie1 = await _decided_fact(c, "d_tie1", "4")
        for f in (used, idle, decided, tie1):
            await _anchor(c, f, CODE)
        # `used` is used by decisions' reads / re-asserts: re-assert from other agents makes it stronger
        for agent in ("bob", "carol", "dave"):
            await ok(
                c, "assert_fact", agent_id=agent, subject="Payments", predicate="a_used", value="1",
                scope="project:acme",
            )  # fmt: skip
        await ok(c, "mark_changed", agent_id="hook", changes=[{"path": CODE, "new_hash": "h1"}], commit="c1")
        todo = await ok(c, "facts_to_verify", agent_id="bob")
        order = [x["fact_id"] for x in todo["facts"]]
        assert order[0] == decided, "facts with live decisions come first"
        assert order.index(used) < order.index(idle), "then the more active fact"
        by = {x["fact_id"]: x for x in todo["facts"]}
        assert by[used]["activation"] > by[idle]["activation"]
        assert all("protected" in x for x in todo["facts"])
        # Listing the work does not strengthen what it lists
        before = rows(client, tenant, "MATCH ()-[r:READ]->() RETURN count(r)")[0][0]
        await ok(c, "facts_to_verify", agent_id="bob")
        assert rows(client, tenant, "MATCH ()-[r:READ]->() RETURN count(r)")[0][0] == before


async def test_facts_to_verify_has_no_activation_when_forgetting_is_off(server, client, tenant, monkeypatch):
    async with Client(server) as c:
        f = await _decided_fact(c, "timeout", "30 seconds")
        await _anchor(c, f)
        await ok(c, "mark_changed", agent_id="hook", changes=[{"path": CODE, "new_hash": "h1"}], commit="c1")
        monkeypatch.setenv("PLEXUS_FORGETTING", "off")
        todo = await ok(c, "facts_to_verify", agent_id="bob")
        assert [x["fact_id"] for x in todo["facts"]] == [f]
        assert "activation" not in todo["facts"][0]


async def test_a_verification_is_a_weight_2_activation_event(server, client, tenant):
    async with Client(server) as c:
        f = await _decided_fact(c, "timeout", "30 seconds")
        await _anchor(c, f)
        g = graph_name(tenant)
        act = Activation(client, g)
        before = act.compute([f])[f]
        await ok(c, "verify_fact", agent_id="bob", fact_id=f, still_true=True)
        after = act.compute([f])[f]
        assert [e.kind for e in after.events].count("verified") == 1
        assert [e.w for e in after.events if e.kind == "verified"] == [2]
        assert after.activation > before.activation
        s = (await ok(c, "memory_strength", agent_id="bob", fact_id=f))["strength"]
        assert s["counts"]["verified"] == 1


async def test_a_changed_verification_counts_on_the_old_fact_too(server, client, tenant):
    async with Client(server) as c:
        f = await _decided_fact(c, "timeout", "30 seconds")
        await _anchor(c, f)
        await ok(c, "mark_changed", agent_id="hook", changes=[{"path": CODE, "new_hash": "h1"}])
        v = await ok(c, "verify_fact", agent_id="bob", fact_id=f, still_true=False, new_value="60 seconds")
        act = Activation(client, graph_name(tenant)).compute([f, v["new_fact_id"]])
        assert [e.kind for e in act[f].events].count("verified") == 1


async def test_recalling_a_suspect_fact_does_not_strengthen_it(server, client, tenant):
    async with Client(server) as c:
        f = await _decided_fact(c, "timeout", "30 seconds")
        await _anchor(c, f)
        await ok(c, "mark_changed", agent_id="hook", changes=[{"path": CODE, "new_hash": "h1"}], commit="c1")
        act = Activation(client, graph_name(tenant))
        before = act.compute([f])[f].activation
        for _ in range(3):
            r = await ok(c, "recall", agent_id="bob", query="payments timeout", scope="project:acme")
            assert any(x["fact_id"] == f for x in r["facts"])
        assert act.compute([f])[f].activation == before


async def test_memory_sweep_never_touches_a_suspect_fact(server, client, tenant):
    async with Client(server) as c:
        suspect = await _decided_fact(c, "timeout", "30 seconds")
        plain = await _decided_fact(c, "retries", "3")
        await _anchor(c, suspect)
        await ok(c, "mark_changed", agent_id="hook", changes=[{"path": CODE, "new_hash": "h1"}], commit="c1")
        # age both facts far into the past so that both are faint
        long_ago = now_ms() - 400 * 86_400_000
        client.graph(graph_name(tenant)).query(
            "MATCH (f:Fact) WHERE f.id IN $ids SET f.created_at = $t",
            {"ids": [suspect, plain], "t": long_ago},
        )
        client.graph(graph_name(tenant)).query("MATCH ()-[a:ASSERTED_BY]->() SET a.at = $t", {"t": long_ago})
        res = (
            await ok(c, "memory_sweep", agent_id="bob", scope="project:acme", dry_run=False, threshold=50.0)
        )["sweep"]
        moved = set(res["moved"])
        assert plain in moved and suspect not in moved
        status = {r[0]: r[1] for r in rows(client, tenant, "MATCH (f:Fact) RETURN f.id, f.status")}
        assert status[suspect] == "active" and status[plain] == "dormant"
