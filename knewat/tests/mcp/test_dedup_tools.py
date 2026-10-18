"""MCP contract tests for the soft-duplicate tools (P9-c B2): confirm_duplicate, reject_duplicate and the
``possible_duplicates`` / ``maybe_duplicate_of`` fields. Uses the hash embedder: the pairs below are linked by token
overlap (same words in another order), which is what the soft tier is for."""

# ruff: noqa: E501 - long literal tables and prose lines

from __future__ import annotations

from mcp import Client

from .test_tool_coverage import audit_links, err, ok, rows, tool_calls


async def _pair(c: Client, a="Service A calls B", b="Service B calls A", agent1="alice", agent2="bob"):
    o = await ok(c, "assert_fact", agent_id=agent1, subject="Topology", predicate="edge", value=a)
    n = await ok(c, "assert_fact", agent_id=agent2, subject="Topology", predicate="edge", value=b)
    return o, n


async def test_assert_reports_possible_duplicates_and_recall_carries_the_link(server):
    async with Client(server) as c:
        o, n = await _pair(c)
        assert n["duplicate_of"] is None and n["fact_id"] != o["fact_id"]
        assert [d["fact_id"] for d in n["possible_duplicates"]] == [o["fact_id"]]
        assert n["possible_duplicates"][0]["value"] == "Service A calls B"
        assert o["possible_duplicates"] == []
        res = await ok(c, "recall", agent_id="carol", query="Topology edge Service calls", k=5)
        by = {f["fact_id"]: f for f in res["facts"]}
        assert by[n["fact_id"]]["maybe_duplicate_of"] == [o["fact_id"]]
        assert by[o["fact_id"]].get("maybe_duplicate_of", []) == []  # compact: [] is left out


async def test_confirm_merges_new_into_old_and_reject_undoes_it(server, client, tenant):
    async with Client(server) as c:
        o, n = await _pair(c)
        r = await ok(c, "confirm_duplicate", agent_id="carol", new_id=n["fact_id"], old_id=o["fact_id"])
        assert r["merged"] is True and r["reopened"] is False
        # bob asserted a different value than alice: nothing of alice's was closed, both were current (a contradiction)
        res = await ok(c, "recall", agent_id="carol", query="Topology edge Service calls", k=5)
        ids = [f["fact_id"] for f in res["facts"]]
        assert o["fact_id"] in ids and n["fact_id"] not in ids  # the merged fact is gone from recall
        who = rows(
            client,
            tenant,
            "MATCH (:Fact {id:$f})-[r:ASSERTED_BY]->(a:Agent) RETURN a.id, r.text ORDER BY a.id",
            f=o["fact_id"],
        )
        assert [w[0] for w in who] == ["alice", "bob"]
        assert dict(who)["bob"] == "Service B calls A"  # the wording of the merged assertion is kept
        assert rows(
            client,
            tenant,
            "MATCH (:Fact {id:$n})-[d:DUPLICATES]->(:Fact {id:$o}) RETURN count(d)",
            n=n["fact_id"],
            o=o["fact_id"],
        ) == [[1]]
        again = await ok(c, "confirm_duplicate", agent_id="carol", new_id=n["fact_id"], old_id=o["fact_id"])
        assert again["merged"] is False and again["already"] is True

        u = await ok(c, "reject_duplicate", agent_id="carol", new_id=n["fact_id"], old_id=o["fact_id"])
        assert u["undone"] is True
        res = await ok(c, "recall", agent_id="carol", query="Topology edge Service calls", k=5)
        assert n["fact_id"] in [f["fact_id"] for f in res["facts"]]
        who = rows(
            client, tenant, "MATCH (:Fact {id:$f})-[r:ASSERTED_BY]->(a:Agent) RETURN a.id", f=o["fact_id"]
        )
        assert who == [["alice"]]
    assert audit_links(client, tenant, "confirm_duplicate") == ["UPDATED:Fact", "UPDATED:Fact"]
    assert len(tool_calls(client, tenant, "confirm_duplicate")) == 2


async def test_confirm_after_the_same_agent_reworded_reopens_the_old_value(server, client, tenant):
    async with Client(server) as c:
        o, n = await _pair(c, agent1="alice", agent2="alice")
        assert n["superseded"] == [o["fact_id"]]  # alice replaced her own earlier value
        r = await ok(c, "confirm_duplicate", agent_id="alice", new_id=n["fact_id"], old_id=o["fact_id"])
        assert r["merged"] and r["reopened"]
        hist = (await ok(c, "fact_history", agent_id="alice", subject="Topology", predicate="edge"))[
            "history"
        ]
        cur = [h for h in hist if h["valid_to"] > 9_000_000_000_000]
        assert [h["fact_id"] for h in cur] == [o["fact_id"]]  # exactly one current fact: the old one
        u = await ok(c, "reject_duplicate", agent_id="alice", new_id=n["fact_id"], old_id=o["fact_id"])
        assert u["undone"] and u["restored"]
        hist = (await ok(c, "fact_history", agent_id="alice", subject="Topology", predicate="edge"))[
            "history"
        ]
        cur = [h for h in hist if h["valid_to"] > 9_000_000_000_000]
        assert [h["fact_id"] for h in cur] == [n["fact_id"]]


async def test_reject_removes_only_the_link(server, client, tenant):
    async with Client(server) as c:
        o, n = await _pair(c)
        r = await ok(c, "reject_duplicate", agent_id="carol", new_id=n["fact_id"], old_id=o["fact_id"])
        assert r["rejected"] is True and r["undone"] is False
        res = await ok(c, "recall", agent_id="carol", query="Topology edge Service calls", k=5)
        assert all(f.get("maybe_duplicate_of", []) == [] for f in res["facts"])
        r2 = await ok(c, "reject_duplicate", agent_id="carol", new_id=n["fact_id"], old_id=o["fact_id"])
        assert r2["rejected"] is False  # idempotent
        text = await err(c, "confirm_duplicate", agent_id="carol", new_id=n["fact_id"], old_id=o["fact_id"])
        assert "confirm_duplicate:" in text and "not linked" in text
    n_facts = rows(client, tenant, "MATCH (f:Fact) RETURN count(f)")
    assert n_facts == [[2]]


async def test_bad_ids_are_clear_errors(server):
    async with Client(server) as c:
        text = await err(c, "confirm_duplicate", agent_id="a", new_id="nope", old_id="nada")
        assert "confirm_duplicate:" in text and "unknown fact" in text
        o, _ = await _pair(c)
        text = await err(c, "reject_duplicate", agent_id="a", new_id=o["fact_id"], old_id=o["fact_id"])
        assert "different facts" in text
