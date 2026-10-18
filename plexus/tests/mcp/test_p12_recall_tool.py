"""P12 fix 1 through the MCP tool: recall's default scope is 'all', the defaults hold ~20 facts, and the
result says when something was left out."""

from __future__ import annotations

import json

from mcp import Client
from plexus.graph.tenancy import graph_name


async def ok(c: Client, tool: str, /, **args) -> dict:
    res = await c.call_tool(tool, args)
    assert not res.is_error, res.content[0].text
    return json.loads(res.content[0].text)


async def test_recall_defaults_search_every_scope(server, client, tenant):
    async with Client(server) as c:
        for n in range(1, 21):
            bolt = {"subject": f"Bolt Billing API S{n:02d}", "predicate": "billing_cycle"}
            await ok(c, "assert_fact", agent_id="p", **bolt, value=f"weekly, invoiced on day {n}",
                     scope=f"project:billing-s{n:02d}")  # fmt: skip
            acme = {"subject": f"Acme Notes API S{n:02d}", "predicate": "api_version"}
            await ok(c, "assert_fact", agent_id="p", **acme, value=f"v{2 * n}")
        q = "billing cycle of the Bolt Billing API decided in sprint S07"
        got = await ok(c, "recall", agent_id="r", query=q, step=1)
        assert got["scope_id"] == "all"
        assert got["facts"][0]["entity"] == "Bolt Billing API S07"
        assert got["facts"][0]["value"] == "weekly, invoiced on day 7"
        assert got["count"] == 20 and got["truncated"] is True and got["more_available"] is True
        # trials-int: the D-013 ranking inputs (entity_match, sep, lures, ...) stay out of the compact hit.
        # On near-identical sprint facts `lures` alone is ~20 fact ids a hit and tripled the L8 response size.
        compact = {"fact_id", "entity", "predicate", "value", "valid_from", "score", "by"}
        assert all(set(f) <= compact for f in got["facts"]), got["facts"][0]
        full = await ok(c, "recall", agent_id="r", query=q, detail="full")
        assert {"entity_match", "sep", "lures", "salience"} <= set(full["facts"][0])
        # an explicit 'global' keeps the old meaning: global and what it inherits, not the project scopes
        glob = await ok(c, "recall", agent_id="r", query=q, scope="global")
        assert all(not f["entity"].startswith("Bolt") for f in glob["facts"])
        rec = (
            client.graph(graph_name(tenant))
            .ro_query("MATCH (r:Recall {id: $id}) RETURN r.scope_id, r.k", {"id": got["recall_id"]})
            .result_set
        )
        assert rec == [["all", 20]]


async def test_recall_scope_all_on_an_empty_tenant(server):
    async with Client(server) as c:
        got = await ok(c, "recall", agent_id="r", query="anything")
        assert got["facts"] == [] and got["count"] == 0 and got["truncated"] is False
