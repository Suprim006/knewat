"""P9-int: ``why``, ``forget_source``, ``quarantine_source``, ``release_quarantine`` and
``blocked_by_failure`` expose ``depth`` (L6-B scored 16/24 because the tool could not be asked for depth 12).
Defaults are unchanged."""

from __future__ import annotations

from knewat.graph.tenancy import graph_name
from mcp import Client
from tests.lineage.diamond import build_lineage

from .test_tool_coverage import err, ok


async def _chain(c: Client, client, tenant) -> dict:
    await ok(
        c, "add_source", agent_id="a", title="seed", uri="https://x.example/seed"
    )  # creates the tenant graph
    return build_lineage(client, graph_name(tenant), levels=12, width=1, fan_in=1)


async def test_why_depth_follows_the_chain_to_12(server, client, tenant):
    async with Client(server) as c:
        d = await _chain(c, client, tenant)
        default = (await ok(c, "why", agent_id="a", node_id=d["decision"]))["why"]
        deep = (await ok(c, "why", agent_id="a", node_id=d["decision"], depth=12))["why"]
        shallow = (await ok(c, "why", agent_id="a", node_id=d["decision"], depth=2))["why"]
        ids = lambda w: {n["id"] for n in w["nodes"]}  # noqa: E731
        assert d["source"] in ids(deep) and d["source"] not in ids(default)
        assert len(ids(shallow)) < len(ids(default)) < len(ids(deep))
        await err(c, "why", agent_id="a", node_id=d["decision"], depth=13)


async def test_quarantine_forget_and_release_take_depth(server, client, tenant):
    async with Client(server) as c:
        d = await _chain(c, client, tenant)
        q3 = (await ok(c, "quarantine_source", agent_id="a", source_id=d["source"], depth=3))["quarantined"]
        assert len(q3["fact_ids"]) == 3
        # release with a smaller depth than the quarantine leaves nothing behind that it did not touch
        r3 = (await ok(c, "release_quarantine", agent_id="a", source_id=d["source"], depth=3))["released"]
        assert sorted(r3["fact_ids"]) == sorted(q3["fact_ids"])
        q_default = (await ok(c, "quarantine_source", agent_id="a", source_id=d["source"]))["quarantined"]
        assert len(q_default["fact_ids"]) == 8  # default depth 8
        await ok(c, "release_quarantine", agent_id="a", source_id=d["source"])
        q12 = (await ok(c, "quarantine_source", agent_id="a", source_id=d["source"], depth=12))["quarantined"]
        assert len(q12["fact_ids"]) == 12
        await ok(c, "release_quarantine", agent_id="a", source_id=d["source"], depth=12)
        f2 = (await ok(c, "forget_source", agent_id="a", source_id=d["source"], depth=2))["forgotten"]
        assert len(f2["fact_ids"]) == 2
        f12 = (await ok(c, "forget_source", agent_id="a", source_id=d["source"], depth=12))["forgotten"]
        assert len(f12["fact_ids"]) >= 10  # the remaining ones (two are already forgotten)
        await err(c, "forget_source", agent_id="a", source_id=d["source"], depth=13)
        await err(c, "quarantine_source", agent_id="a", source_id=d["source"], depth=0)


async def test_blocked_by_failure_depth(server):
    async with Client(server) as c:
        tasks = [{"id": "t0", "title": "root"}] + [
            {"id": f"t{i}", "title": f"t{i}", "depends_on": [f"t{i - 1}"]} for i in range(1, 7)
        ]
        await ok(c, "create_tasks", agent_id="a", tasks=tasks)
        every = await ok(c, "blocked_by_failure", agent_id="a", task_id="t0")
        assert every["count"] == 6
        near = await ok(c, "blocked_by_failure", agent_id="a", task_id="t0", depth=2)
        assert near["blocked"] == ["t1", "t2"]
        await err(c, "blocked_by_failure", agent_id="a", task_id="t0", depth=51)
