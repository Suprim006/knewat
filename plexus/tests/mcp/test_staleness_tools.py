"""MCP contract tests for the staleness tools (P7-J): anchor_fact, describe_code, mark_changed, verify_fact,
facts_to_verify, docs_to_update, set_review_date."""

from __future__ import annotations

from mcp import Client

from .test_tool_coverage import audit_links, err, ok, rows

P = "C:/repo/app/payments.py"
DOC = "C:/repo/docs/payments.md"


async def _fact(c: Client, predicate="timeout", value="30 seconds", agent="alice"):
    r = await ok(c, "assert_fact", agent_id=agent, subject="Payments", predicate=predicate, value=value)
    return r["fact_id"]


async def test_the_whole_staleness_loop_through_mcp(server, client, tenant):
    async with Client(server) as c:
        f = await _fact(c)
        doc = (await ok(c, "add_source", agent_id="alice", title="Payments doc", uri=DOC, kind="doc"))[
            "source_id"
        ]
        a = await ok(c, "anchor_fact", agent_id="alice", fact_id=f, path=P.replace("/", "\\"), hash="h0")
        assert a["path"] == P and a["fact_id"] == f and a["anchor_id"].startswith("anc:")
        d = await ok(c, "describe_code", agent_id="alice", source_id=doc, path=P)
        assert d["anchor_id"] == a["anchor_id"]
        await ok(c, "register_agent", agent_id="alice")
        await ok(c, "create_tasks", agent_id="alice", tasks=[{"id": "t1", "title": "ship"}])
        dec = (
            await ok(
                c, "record_decision", agent_id="alice", task_id="t1", text="keep it", based_on_fact_ids=[f]
            )
        )["decision_id"]

        base = await ok(c, "mark_changed", agent_id="hook", changes=[{"path": P, "new_hash": "h0"}])
        assert base["change_id"] is None and base["suspect_fact_ids"] == [] and base["unchanged"] == 1
        out = await ok(
            c, "mark_changed", agent_id="hook", changes=[{"path": P, "new_hash": "h1"}], commit="abc123"
        )
        assert out["suspect_fact_ids"] == [f] and out["change_id"] and out["truncated"] is False
        assert out["decisions"] == [{"id": dec, "text": "keep it"}] and out["decisions_total"] == 1
        assert out["docs_to_update"] == [{"source_id": doc, "uri": DOC, "anchor": P}]
        assert out["tool_call_id"]

        todo = await ok(c, "facts_to_verify", agent_id="bob")
        assert todo["count"] == 1
        row = todo["facts"][0]
        assert (
            row["fact_id"] == f
            and row["reason"] == f"changed in abc123 ({P})"
            and row["decisions_count"] == 1
        )
        docs = await ok(c, "docs_to_update", agent_id="bob")
        assert [x["source_id"] for x in docs["docs"]] == [doc] and docs["docs"][0]["changes"][0][
            "commit"
        ] == "abc123"

        v = await ok(c, "verify_fact", agent_id="bob", fact_id=f, still_true=False, new_value="60 seconds")
        assert v["outcome"] == "changed" and v["flagged_decisions"] == [dec] and v["new_fact_id"] != f
        assert (await ok(c, "facts_to_verify", agent_id="bob"))["count"] == 0
        hist = (await ok(c, "fact_history", agent_id="bob", subject="Payments", predicate="timeout"))[
            "history"
        ]
        assert [h["value"] for h in hist] == ["30 seconds", "60 seconds"]

        c2 = await ok(
            c, "verify_fact", agent_id="bob", fact_id=v["new_fact_id"], still_true=True, commit="abc124"
        )
        assert c2["outcome"] == "confirmed"

        rd = await ok(c, "set_review_date", agent_id="bob", fact_id=v["new_fact_id"], verify_after=1)
        assert rd["verify_after"] == 1
        due = await ok(c, "facts_to_verify", agent_id="bob")
        assert [x["reason"] for x in due["facts"]] == ["review date passed"]

    # audit: ToolCall edges and Step WROTE edges
    assert audit_links(client, tenant, "mark_changed") == ["CREATED:Change", "UPDATED:Fact"]
    assert audit_links(client, tenant, "anchor_fact") == ["CREATED:CodeAnchor", "UPDATED:Fact"]
    assert audit_links(client, tenant, "describe_code") == ["UPDATED:CodeAnchor", "UPDATED:Source"]
    assert audit_links(client, tenant, "verify_fact") == [
        "CREATED:Fact",
        "UPDATED:Decision",
        "UPDATED:Fact",
        "UPDATED:Fact",
    ]
    assert audit_links(client, tenant, "facts_to_verify") == []  # reads write nothing
    wrote = rows(
        client,
        tenant,
        "MATCH (t:ToolCall {tool:'mark_changed'})-[:IN_STEP]->(s:Step)-[:WROTE]->(x) "
        "RETURN labels(x)[0], x.id",
    )
    assert wrote == [["Fact", f]]
    vwrote = rows(
        client,
        tenant,
        "MATCH (:ToolCall {tool:'verify_fact'})-[:IN_STEP]->(s:Step)-[:WROTE]->(x) "
        "RETURN labels(x)[0], count(x) ORDER BY labels(x)[0]",
    )
    assert ["Fact", 3] in vwrote  # old + new fact of the first call, the new fact again in the second
    # suspicion is explainable: Change -[:SUSPECTED]-> Fact
    assert rows(client, tenant, "MATCH (c:Change)-[:SUSPECTED]->(f:Fact {id:$f}) RETURN c.commit", f=f) == [
        ["abc123"]
    ]


async def test_errors_are_clear_and_nothing_is_written(server, client, tenant):
    async with Client(server) as c:
        f = await _fact(c)
        assert "no-such-fact" in await err(c, "anchor_fact", agent_id="a", fact_id="no-such-fact", path=P)
        assert "no-such-source" in await err(
            c, "describe_code", agent_id="a", source_id="no-such-source", path=P
        )
        assert "absolute" in await err(c, "anchor_fact", agent_id="a", fact_id=f, path="rel/x.py")
        assert "absolute" in await err(
            c, "mark_changed", agent_id="a", changes=[{"path": "x.py", "new_hash": "h"}]
        )
        assert "no-such-fact" in await err(
            c, "verify_fact", agent_id="a", fact_id="no-such-fact", still_true=True
        )
        assert "new_value" in await err(c, "verify_fact", agent_id="a", fact_id=f, still_true=False)
        assert "no-such-fact" in await err(
            c, "set_review_date", agent_id="a", fact_id="no-such-fact", verify_after=5
        )
        assert "limit" in await err(c, "facts_to_verify", agent_id="a", limit=0)
    assert rows(client, tenant, "MATCH (a:CodeAnchor) RETURN count(a)") == [[0]]
    assert rows(client, tenant, "MATCH (c:Change) RETURN count(c)") == [[0]]
    assert audit_links(client, tenant, "mark_changed") == []


async def test_argument_limits_are_enforced_with_short_messages(server):
    async with Client(server) as c:
        too_many = [{"path": f"C:/r/f{i}.py", "new_hash": "h"} for i in range(201)]
        text = await err(c, "mark_changed", agent_id="a", changes=too_many)
        assert "changes" in text and len(text) < 400
        assert "path" in await err(c, "anchor_fact", agent_id="a", fact_id="f", path="C:/" + "x" * 1030)
        assert "hash" in await err(c, "anchor_fact", agent_id="a", fact_id="f", path=P, hash="h" * 129)
        assert "fact_id" in await err(c, "anchor_fact", agent_id="a", fact_id="x" * 129, path=P)
        text = await err(
            c, "mark_changed", agent_id="a", changes=[{"path": P, "new_hash": "h", "dependsOn": 1}]
        )
        assert "unknown key" in text and "new_hash" in text
        assert "changes" in await err(c, "mark_changed", agent_id="a", changes=[])
        assert "verify_after" in await err(c, "set_review_date", agent_id="a", fact_id="f", verify_after=-1)
        assert "limit" in await err(c, "docs_to_update", agent_id="a", limit=201)


async def test_a_function_level_change_only_touches_that_functions_facts(server, client, tenant):
    async with Client(server) as c:
        on_f = await _fact(c, "f behaviour", "adds")
        on_g = await _fact(c, "g behaviour", "subtracts")
        await ok(c, "anchor_fact", agent_id="a", fact_id=on_f, path=P, symbol="f")
        await ok(c, "anchor_fact", agent_id="a", fact_id=on_g, path=P, symbol="g")
        base = [
            {"path": P, "new_hash": "file0"},
            {"path": P, "symbol": "f", "new_hash": "f0"},
            {"path": P, "symbol": "g", "new_hash": "g0"},
        ]
        await ok(c, "mark_changed", agent_id="a", changes=base)
        out = await ok(
            c,
            "mark_changed",
            agent_id="a",
            changes=[
                {"path": P, "new_hash": "file1"},
                {"path": P, "symbol": "f", "new_hash": "f1", "kind": "function"},
                {"path": P, "symbol": "g", "new_hash": "g0"},
            ],
        )
        assert out["suspect_fact_ids"] == [on_f]
