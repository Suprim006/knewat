"""P9-f: the MCP ``why`` tool exposes ``depth`` and ``max_elements`` (Crucible L6-B: chains deeper than 6 were
unanswerable through the tool although ``Lineage.why(depth=12)`` answers them)."""

from __future__ import annotations

from mcp import Client
from plexus.graph.tenancy import graph_name
from tests.lineage.diamond import build_lineage

from .test_tool_coverage import err, ok


async def test_why_tool_takes_depth_and_max_elements(server, client, tenant):
    async with Client(server) as c:
        await ok(c, "add_source", agent_id="a", title="seed", uri="urn:seed")  # creates the tenant graph
        d = build_lineage(
            client, graph_name(tenant), levels=10, width=1, fan_in=1
        )  # f10-0 -> ... -> f1-0 -> src

        def reaches_source(w: dict) -> bool:
            return any(e["to"] == d["source"] for e in w["edges"])

        default = (await ok(c, "why", agent_id="a", node_id=d["decision"]))["why"]
        assert not reaches_source(default)  # depth 6 (unchanged default) stops 4 hops short
        deep = (await ok(c, "why", agent_id="a", node_id=d["decision"], depth=12))["why"]
        assert reaches_source(deep) and deep["truncated"] is False
        small = (await ok(c, "why", agent_id="a", node_id=d["decision"], depth=12, max_elements=4))["why"]
        assert small["truncated"] is True and len(small["nodes"]) + len(small["edges"]) <= 4
        assert "depth" in await err(c, "why", agent_id="a", node_id=d["decision"], depth=13)
        assert "max_elements" in await err(c, "why", agent_id="a", node_id=d["decision"], max_elements=1)
