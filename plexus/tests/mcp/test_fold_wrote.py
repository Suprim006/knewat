"""P9-int: assert_fact / record_decision / handoff create ``(Step)-[:WROTE]->(node)`` in their own
write statement."""

from __future__ import annotations

from mcp import Client

from .test_tool_coverage import err, ok, rows


async def test_the_three_tools_fold_wrote_and_leave_no_extra_steps(server, client, tenant):
    async with Client(server) as c:
        await ok(c, "register_agent", agent_id="a", role="builder")
        await ok(c, "register_agent", agent_id="b", role="builder")
        await ok(c, "create_tasks", agent_id="a", tasks=[{"id": "t1", "title": "x"}])
        f = (await ok(c, "assert_fact", agent_id="a", subject="Cache", predicate="engine", value="Redis"))[
            "fact_id"
        ]
        dup = await ok(c, "assert_fact", agent_id="a", subject="Cache", predicate="engine", value="Redis")
        assert dup["duplicate_of"] == f
        d = (
            await ok(c, "record_decision", agent_id="a", task_id="t1", text="use it", based_on_fact_ids=[f])
        )["decision_id"]
        h = (await ok(c, "handoff", agent_id="a", to_agent="b", task_id="t1", note="n", fact_ids=[f]))[
            "handoff_id"
        ]
    for node in (f, d, h):
        got = rows(
            client,
            tenant,
            "MATCH (s:Step)-[w:WROTE]->(x {id: $i}) RETURN count(w), count(DISTINCT s)",
            i=node,
        )
        assert got == [[1, 1]], (node, got)
    # one Step per successful call (create_tasks, 2 asserts, decision, handoff, 2 registers)
    assert rows(client, tenant, "MATCH (s:Step) RETURN count(s)")[0][0] >= 6
    # the decision's READ edge on its fact is still linked after the write
    assert rows(
        client, tenant, "MATCH (:Step)-[r:READ {via: 'use'}]->(:Fact {id: $i}) RETURN count(r) > 0", i=f
    ) == [[True]]


async def test_a_rejected_call_leaves_no_step(server, client, tenant):
    async with Client(server) as c:
        await ok(c, "register_agent", agent_id="a", role="builder")
        steps = rows(client, tenant, "MATCH (s:Step) RETURN count(s)")[0][0]
        await err(c, "record_decision", agent_id="a", task_id="nope", text="x", based_on_fact_ids=[])
        await err(
            c, "assert_fact", agent_id="a", subject="S", predicate="p", value="v", source_id="no-such-source"
        )
        await err(c, "handoff", agent_id="a", to_agent="ghost", task_id="nope", note="x")
        assert rows(client, tenant, "MATCH (s:Step) RETURN count(s)")[0][0] == steps
        assert rows(client, tenant, "MATCH (s:Step) WHERE NOT (s)-[:BY]->() RETURN count(s)")[0][0] == 0
        # numbering is not burnt by the failed calls
        await ok(c, "assert_fact", agent_id="a", subject="S", predicate="p", value="v")
        got = rows(client, tenant, "MATCH (s:Step {agent_id: 'a'}) RETURN max(s.n), count(s)")[0]
        assert got[0] == got[1]
