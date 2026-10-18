"""Slice 1: every READ edge says HOW the fact was read ('recall' = surfaced, 'use' = acted on) and WHEN."""

from __future__ import annotations

from .conftest import reads


def _fact(eng, scope, value="PostgreSQL 16", now=1000):
    return eng.assert_fact("API", "database", value, scope, "alice", now=now)["fact_id"]


def test_record_recall_writes_read_via_recall_with_at(eng, lin, scope, client, graph):
    f = _fact(eng, scope)
    st = lin.record_step("alice", 1, at=5000)
    lin.record_recall("alice", st, "database", scope, 3, [{"fact_id": f, "score": 0.1}], now=5000)
    assert reads(client, graph, st, f) == [["recall", 5000]]


def test_record_recall_twice_keeps_one_read_edge_and_refreshes_at(eng, lin, scope, client, graph):
    f = _fact(eng, scope)
    st = lin.record_step("alice", 1, at=5000)
    for now in (5000, 6000):
        lin.record_recall("alice", st, "database", scope, 3, [{"fact_id": f, "score": 0.1}], now=now)
    assert reads(client, graph, st, f) == [["recall", 6000]]


def test_link_step_read_is_a_use_stamped_with_the_step_time(eng, lin, scope, client, graph):
    f = _fact(eng, scope)
    st = lin.record_step("alice", 1, at=7000)
    lin.link_step(st, read_ids=[f])
    assert reads(client, graph, st, f) == [["use", 7000]]


def test_use_is_never_downgraded_by_a_later_recall(eng, lin, scope, client, graph):
    f = _fact(eng, scope)
    st = lin.record_step("alice", 1, at=7000)
    lin.link_step(st, read_ids=[f])
    lin.record_recall("alice", st, "database", scope, 3, [{"fact_id": f, "score": 0.1}], now=8000)
    assert reads(client, graph, st, f) == [["use", 8000]]


def test_recall_then_use_upgrades_the_same_edge(eng, lin, scope, client, graph):
    f = _fact(eng, scope)
    st = lin.record_step("alice", 1, at=7000)
    lin.record_recall("alice", st, "database", scope, 3, [{"fact_id": f, "score": 0.1}], now=7000)
    lin.link_step(st, read_ids=[f])
    assert reads(client, graph, st, f) == [["use", 7000]]
    n = client.graph(graph).ro_query("MATCH ()-[r:READ]->() RETURN count(r)").result_set
    assert n == [[1]]


def test_link_assert_result_duplicate_and_supersede_reads_are_uses(eng, lin, scope, client, graph):
    f1 = _fact(eng, scope, "PostgreSQL 16", now=1000)
    st = lin.record_step("alice", 1, at=9000)
    r = eng.assert_fact("API", "database", "PostgreSQL 16", scope, "bob", now=9000)  # duplicate
    lin.link_assert_result(st, r)
    assert r["duplicate_of"] == f1
    assert reads(client, graph, st, f1) == [["use", 9000]]
    st2 = lin.record_step("bob", 1, at=9500)
    r2 = eng.assert_fact("API", "database", "PostgreSQL 17", scope, "alice", now=9500, supersede=True)
    lin.link_assert_result(st2, r2)
    assert r2["superseded"] == [f1]
    assert reads(client, graph, st2, f1) == [["use", 9500]]
