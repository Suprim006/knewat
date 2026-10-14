from __future__ import annotations

import pytest


def _chain(client, graph, session_id):
    """Episode texts in NEXT order starting from the episode with no incoming NEXT."""
    rows = client.graph(graph).ro_query(
        "MATCH (:Session {id:$s})-[:HAS_EPISODE]->(e:Episode) WHERE NOT (:Episode)-[:NEXT]->(e) "
        "WITH e MATCH p = (e)-[:NEXT*0..]->(x:Episode) WITH x, length(p) AS d "
        "ORDER BY d RETURN x.text",
        {"s": session_id},
    )
    return [r[0] for r in rows.result_set]


def test_start_session_creates_agent_session_had(eng, client, graph):
    sid = eng.start_session("planner-1", "planner", harness="claude-code")
    rows = client.graph(graph).ro_query(
        "MATCH (a:Agent {id:'planner-1'})-[:HAD]->(s:Session {id:$s}) RETURN a.role, a.harness, s.agent_id",
        {"s": sid},
    )
    assert rows.result_set == [["planner", "claude-code", "planner-1"]]
    # starting again reuses the agent
    eng.start_session("planner-1", "planner")
    n = client.graph(graph).ro_query("MATCH (a:Agent {id:'planner-1'}) RETURN count(a)").result_set[0][0]
    assert n == 1


def test_episode_chain_order_across_two_sessions(eng, client, graph):
    s1 = eng.start_session("a1", "builder")
    s2 = eng.start_session("a2", "researcher")
    # interleave writes on the two sessions
    for i in range(4):
        eng.remember_episode(s1, "user", f"s1 msg {i}", step=i)
        eng.remember_episode(s2, "assistant", f"s2 msg {i}", step=i)
    assert _chain(client, graph, s1) == [f"s1 msg {i}" for i in range(4)]
    assert _chain(client, graph, s2) == [f"s2 msg {i}" for i in range(4)]
    # each chain has exactly one head and one NEXT edge fewer than episodes
    nxt = client.graph(graph).ro_query("MATCH (:Episode)-[r:NEXT]->(:Episode) RETURN count(r)").result_set[0][0]
    assert nxt == 6


def test_episode_stores_embedding_step_and_prev(eng, client, graph):
    s = eng.start_session("a1", "builder")
    e1 = eng.remember_episode(s, "user", "hello world", step=7)
    e2 = eng.remember_episode(s, "assistant", "hi")
    r = client.graph(graph).ro_query(
        "MATCH (e:Episode {id:$id}) RETURN e.step, e.role, e.embedding IS NOT NULL", {"id": e1}
    )
    assert r.result_set[0][0] == 7 and r.result_set[0][1] == "user"
    r = client.graph(graph).ro_query("MATCH (a:Episode {id:$a})-[:NEXT]->(b:Episode {id:$b}) RETURN b.step", {"a": e1, "b": e2})
    assert r.result_set == [[-1]]


def test_remember_episode_unknown_session(eng):
    with pytest.raises(LookupError):
        eng.remember_episode("nope", "user", "x")
