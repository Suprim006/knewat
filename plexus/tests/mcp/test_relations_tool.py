"""MCP contract for ``assert_relation`` and ``recall(hops)`` (P9-b / P2)."""

from __future__ import annotations

from mcp import Client

from .test_tool_coverage import audit_links, err, ok, rows


async def _build(c):
    await ok(
        c, "assert_fact", agent_id="a", subject="Payment Service", predicate="latency", value="p99 is 120 ms"
    )
    await ok(
        c, "assert_fact", agent_id="a", subject="Ledger DB", predicate="engine", value="postgres sixteen"
    )
    await ok(
        c,
        "assert_fact",
        agent_id="a",
        subject="Backup Vault",
        predicate="retention",
        value="ninety days nightly snapshot cold storage",
    )
    r1 = await ok(
        c, "assert_relation", agent_id="a", subject="Payment Service", kind="depends on", object="Ledger DB"
    )
    r2 = await ok(
        c, "assert_relation", agent_id="a", subject="Ledger DB", kind="backed up by", object="Backup Vault"
    )
    return r1, r2


async def test_assert_relation_and_recall_hops_through_mcp(server, client, tenant):
    async with Client(server) as c:
        r1, r2 = await _build(c)
        assert r1["created"] is True and r1["kind"] == "depends on" and r1["subject_id"] != r1["object_id"]
        again = await ok(
            c,
            "assert_relation",
            agent_id="a",
            subject="payment service",
            kind="Depends On",
            object="ledger db",
        )
        assert again["created"] is False and again["subject_id"] == r1["subject_id"]

        q = "Payment Service latency"
        plain = await ok(c, "recall", agent_id="b", query=q, k=1, forgetting=False)
        assert [f["value"] for f in plain["facts"]] == ["p99 is 120 ms"]
        zero = await ok(c, "recall", agent_id="b", query=q, k=1, forgetting=False, hops=0)
        assert [f["fact_id"] for f in zero["facts"]] == [f["fact_id"] for f in plain["facts"]]
        assert all("hop" not in f for f in zero["facts"])
        two = await ok(c, "recall", agent_id="b", query=q, k=1, forgetting=False, hops=2)
        assert [f["entity"] for f in two["facts"]] == ["Payment Service", "Ledger DB", "Backup Vault"]
        assert [f.get("hop") for f in two["facts"]] == [None, 1, 2]
        assert [e["kind"] for e in two["facts"][2]["relation_path"]] == ["depends on", "backed up by"]
        assert two["recall_id"]  # the recall is recorded like any other (why_recalled works on it)

        assert "hops" in await err(c, "recall", agent_id="b", query=q, hops=3)
        assert "kind" in await err(c, "assert_relation", agent_id="a", subject="A", kind="", object="B")
        assert "same entity" in await err(
            c, "assert_relation", agent_id="a", subject="A", kind="uses", object="a"
        )
    assert audit_links(client, tenant, "assert_relation") == ["UPDATED:Entity"] * 6  # 2 entities x 3 calls
    n = rows(client, tenant, "MATCH (:Entity)-[r:RELATES]->(:Entity) RETURN count(r)")
    assert n == [[2]]


async def test_assert_relation_in_an_unknown_scope_is_refused_and_writes_nothing(server, client, tenant):
    async with Client(server) as c:
        text = await err(
            c, "assert_relation", agent_id="a", subject="A", kind="uses", object="B", scope="no-such-scope-id"
        )
        assert "scope" in text.lower()
    assert rows(client, tenant, "MATCH (e:Entity) RETURN count(e)") == [[0]]  # no orphan entities
