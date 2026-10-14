from __future__ import annotations

from plexus.audit import MAX_LINKS, record_tool_call
from plexus.embed import HashEmbedder
from plexus.engram import Engram


def _edges(client, graph, tc_id):
    res = client.graph(graph).ro_query(
        "MATCH (t:ToolCall {id:$id})-[r]->(n) RETURN type(r) AS rel, labels(n)[0] AS label, n.id AS id",
        {"id": tc_id},
    )
    return {(r[0], r[1], r[2]) for r in res.result_set}


def _props(client, graph, tc_id):
    res = client.graph(graph).ro_query("MATCH (t:ToolCall {id:$i}) RETURN t", {"i": tc_id})
    return res.result_set[0][0].properties


def test_creates_toolcall_with_created_and_updated_edges(client, graph):
    eng = Engram(client, graph, HashEmbedder())
    sid = eng.start_session("a1")
    eid = eng.remember_episode(sid, "user", "hello")
    tc = record_tool_call(
        client,
        graph,
        "remember_episode",
        "a1",
        None,
        "engram/remember_episode",
        1.5,
        created_ids=[("Episode", eid)],
        updated_ids=[("Session", sid), ("Nope", "x")],
        step=3,
        now=42,
    )
    assert _edges(client, graph, tc) == {("CREATED", "Episode", eid), ("UPDATED", "Session", sid)}
    p = _props(client, graph, tc)
    assert p["tool"] == "remember_episode" and p["agent_id"] == "a1" and p["at"] == 42
    assert p["wrote"] is True and p["run_time_ms"] == 1.5 and p["step"] == 3
    assert p["query_name"] == "engram/remember_episode"


def test_read_only_call_has_no_edges_and_wrote_false(client, graph):
    tc = record_tool_call(client, graph, "recall", "a1", None, "engram/recall", 0.5)
    assert _edges(client, graph, tc) == set()
    assert _props(client, graph, tc)["wrote"] is False


def test_unknown_ids_get_no_edge_and_missing_step_is_tolerated(client, graph):
    tc = record_tool_call(client, graph, "x", "a1", "no-such-step", "q", 1, created_ids=[("Fact", "ghost")])
    assert _edges(client, graph, tc) == set()


def test_in_step_edge_when_step_exists(client, graph):
    client.graph(graph).query("CREATE (:Step {id:'s1', n:1, at:1, agent_id:'a1', created_at:1})")
    tc = record_tool_call(client, graph, "x", "a1", "s1", "q", 1)
    assert _edges(client, graph, tc) == {("IN_STEP", "Step", "s1")}


def test_links_are_bounded(client, graph):
    ids = [f"t{i}" for i in range(MAX_LINKS + 50)]
    client.graph(graph).query(
        "UNWIND $ids AS i CREATE (:Task {id:i, title:i, status:'open', priority:0, lease_until:0,"
        " claimed_by:'', version:0, done_at:0, created_at:1})",
        {"ids": ids},
    )
    tc = record_tool_call(
        client, graph, "create_tasks", "a1", None, "relay/create_tasks", 1,
        created_ids=[("Task", i) for i in ids],
    )  # fmt: skip
    assert len(_edges(client, graph, tc)) == MAX_LINKS
