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


# ---------------------------------------------------------------- P12 fix 2: the five task tools
def _wrote(client, tenant, task_id):
    return rows(
        client,
        tenant,
        "MATCH (s:Step)-[w:WROTE]->(x:Task {id: $i}) RETURN s.agent_id, s.n ORDER BY s.n",
        i=task_id,
    )


async def test_task_tools_fold_wrote_one_edge_per_call(server, client, tenant):
    async with Client(server) as c:
        await ok(c, "register_agent", agent_id="a", role="builder")
        await ok(c, "register_agent", agent_id="b", role="builder")
        ids = (
            await ok(
                c,
                "create_tasks",
                agent_id="a",
                tasks=[{"id": "t1", "title": "x"}, {"id": "t2", "title": "y", "depends_on": ["t1"]}],
            )
        )["task_ids"]
        assert ids == ["t1", "t2"]
        # create: every created task has exactly one WROTE, both from the SAME Step
        assert [len(_wrote(client, tenant, i)) for i in ids] == [1, 1]
        assert _wrote(client, tenant, "t1") == _wrote(client, tenant, "t2")
        claimed = (await ok(c, "claim_next_task", agent_id="b"))["task"]
        assert claimed["id"] == "t1"
        assert len(_wrote(client, tenant, "t1")) == 2 and {r[0] for r in _wrote(client, tenant, "t1")} == {
            "a",
            "b",
        }
        failed = await ok(c, "fail_task", agent_id="b", task_id="t1", expected_version=claimed["version"])
        assert len(_wrote(client, tenant, "t1")) == 3
        await ok(c, "reopen_task", agent_id="a", task_id="t1")
        assert len(_wrote(client, tenant, "t1")) == 4
        again = (await ok(c, "claim_next_task", agent_id="a"))["task"]
        done = await ok(
            c,
            "complete_task",
            agent_id="a",
            task_id="t1",
            expected_version=again["version"],
            artifacts=[{"kind": "file", "uri": "x.txt"}],
        )
        assert failed["status"] == "failed" and done["status"] == "done"
        # create, claim, fail, reopen, claim, complete: version 5 = 6 edges, one per call, none twice
        got = rows(
            client,
            tenant,
            "MATCH (t:Task {id: 't1'}) OPTIONAL MATCH (s:Step)-[w:WROTE]->(t) "
            "RETURN t.version, count(w), count(DISTINCT s)",
        )
        assert got == [[5, 6, 6]], got
        # the artifact is not a WROTE target (only Facts / Decisions / Handoffs / Tasks are)
        assert rows(client, tenant, "MATCH (:Step)-[w:WROTE]->(:Artifact) RETURN count(w)") == [[0]]
        # the Task change stays visible in the audit trail of the call
        assert (
            rows(client, tenant, "MATCH (tc:ToolCall {tool: 'claim_next_task'}) RETURN count(tc)")[0][0] == 2
        )


async def test_rejected_task_calls_leave_no_step_and_no_wrote(server, client, tenant):
    async with Client(server) as c:
        await ok(c, "register_agent", agent_id="a", role="builder")
        await ok(c, "create_tasks", agent_id="a", tasks=[{"id": "t1", "title": "x"}])
        got = (await ok(c, "claim_next_task", agent_id="a"))["task"]
        steps = rows(client, tenant, "MATCH (s:Step) RETURN count(s)")[0][0]
        wrote = rows(client, tenant, "MATCH (:Step)-[w:WROTE]->(:Task) RETURN count(w)")[0][0]
        agents = rows(client, tenant, "MATCH (a:Agent) RETURN count(a)")[0][0]
        await err(c, "create_tasks", agent_id="a", tasks=[{"id": "t1", "title": "dup"}])  # duplicate id
        await err(c, "create_tasks", agent_id="a", tasks=[{"id": "t9", "title": "z", "depends_on": ["nope"]}])
        await err(c, "complete_task", agent_id="a", task_id="t1", expected_version=got["version"] + 7)
        await err(c, "fail_task", agent_id="a", task_id="t1", expected_version=got["version"] + 7)
        await err(c, "reopen_task", agent_id="a", task_id="t1")  # not failed
        await err(c, "reopen_task", agent_id="a", task_id="nope")
        # unknown agents are still rejected, and not registered as a side effect of opening a Step
        await err(c, "claim_next_task", agent_id="ghost")
        await err(c, "complete_task", agent_id="ghost", task_id="t1", expected_version=got["version"])
        await err(c, "reopen_task", agent_id="ghost", task_id="t1")
        assert rows(client, tenant, "MATCH (s:Step) RETURN count(s)")[0][0] == steps
        assert rows(client, tenant, "MATCH (:Step)-[w:WROTE]->(:Task) RETURN count(w)")[0][0] == wrote
        assert rows(client, tenant, "MATCH (a:Agent) RETURN count(a)")[0][0] == agents
        assert rows(client, tenant, "MATCH (s:Step) WHERE NOT (s)-[:BY]->() RETURN count(s)")[0][0] == 0
        assert rows(client, tenant, "MATCH (t:Task {id: 't1'}) RETURN t.version, t.status") == [
            [1, "claimed"]
        ]


async def test_nothing_claimable_writes_no_wrote_edge(server, client, tenant):
    async with Client(server) as c:
        await ok(c, "register_agent", agent_id="a", role="builder")
        wrote = rows(client, tenant, "MATCH (:Step)-[w:WROTE]->() RETURN count(w)")[0][0]
        assert (await ok(c, "claim_next_task", agent_id="a"))["task"] is None
        assert rows(client, tenant, "MATCH (:Step)-[w:WROTE]->() RETURN count(w)")[0][0] == wrote
        assert rows(client, tenant, "MATCH ()-[c:CLAIMED]->() RETURN count(c)")[0][0] == 0
