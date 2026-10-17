"""P9-b / P2: typed entity relations and ``recall(hops)``.

The target fact shares no word (and so, with the hash embedder, no embedding mass) with the query; it is only
reachable over ``RELATES`` edges: Payment Service -depends_on-> Ledger DB -backed_up_by-> Backup Vault.
"""

from __future__ import annotations

import pytest

from plexus.engram import Engram, UnknownReference
from plexus.engram import relations as rel

QUERY = "Payment Service latency"
OFF = {"forgetting": False}  # the activation re-rank is time-dependent; equality checks need a fixed order


@pytest.fixture
def world(eng: Engram, glob):
    eng.assert_fact("Payment Service", "latency", "p99 is 120 ms", glob, "a1", now=10)
    eng.assert_fact("Ledger DB", "engine", "postgres sixteen", glob, "a1", now=11)
    eng.assert_fact(
        "Backup Vault", "retention", "ninety days nightly snapshot cold storage", glob, "a1", now=12
    )
    eng.assert_fact("Unrelated Thing", "colour", "teal", glob, "a1", now=13)
    r1 = eng.assert_relation("Payment Service", "depends on", "Ledger DB", glob, now=20)
    r2 = eng.assert_relation("Ledger DB", "backed up by", "Backup Vault", glob, now=21)
    return {"glob": glob, "r1": r1, "r2": r2}


def _values(rows):
    return [r["value"] for r in rows]


# -- assert_relation ------------------------------------------------------------------------------------


def test_assert_relation_creates_one_directed_edge_and_is_idempotent(eng, client, graph, glob):
    a = eng.assert_relation("Payment Service", "Depends  On", "Ledger DB", glob, now=5)
    assert a["created"] is True and a["kind"] == "depends on" and a["subject_id"] != a["object_id"]
    b = eng.assert_relation(
        "payment service", "depends on", "ledger db", glob, now=6
    )  # same entities, same kind
    assert b["created"] is False and (b["subject_id"], b["object_id"]) == (a["subject_id"], a["object_id"])
    rows = (
        client.graph(graph)
        .ro_query("MATCH (a:Entity)-[r:RELATES]->(b:Entity) RETURN a.name, r.kind, r.scope_id, r.at, b.name")
        .result_set
    )
    assert rows == [["Payment Service", "depends on", glob, 5, "Ledger DB"]]
    c = eng.assert_relation("Payment Service", "owned by", "Ledger DB", glob)  # another kind: another edge
    assert c["created"] is True


def test_assert_relation_rejects_bad_input_and_writes_nothing(eng, client, graph, glob):
    with pytest.raises(UnknownReference):
        eng.assert_relation("A", "uses", "B", "no-such-scope")
    with pytest.raises(ValueError, match="kind"):
        eng.assert_relation("A", "  ", "B", glob)
    with pytest.raises(ValueError, match="same entity"):
        eng.assert_relation("A", "uses", "a", glob)
    with pytest.raises(ValueError):
        eng.assert_relation("", "uses", "B", glob)
    n = client.graph(graph).ro_query("MATCH (e:Entity) RETURN count(e)").result_set
    assert n == [[0]]  # no orphan entities from the rejected calls


# -- recall(hops) ---------------------------------------------------------------------------------------


def test_zero_overlap_fact_is_found_at_hops_2_and_not_at_0_or_1(eng, world):
    scope = world["glob"]
    base = eng.recall(QUERY, scope, k=1, **OFF)
    assert _values(base) == ["p99 is 120 ms"]
    assert eng.recall(QUERY, scope, k=1, hops=0, **OFF) == base  # identical rows
    one = eng.recall(QUERY, scope, k=1, hops=1, **OFF)
    assert _values(one) == ["p99 is 120 ms", "postgres sixteen"]
    two = eng.recall(QUERY, scope, k=1, hops=2, **OFF)
    assert _values(two) == ["p99 is 120 ms", "postgres sixteen", "ninety days nightly snapshot cold storage"]
    assert "Unrelated Thing" not in [r["entity"] for r in two]


def test_hop_rows_say_how_they_were_reached_and_direct_rows_are_untouched(eng, world):
    scope = world["glob"]
    base = eng.recall(QUERY, scope, k=1, **OFF)
    two = eng.recall(QUERY, scope, k=1, hops=2, **OFF)
    assert two[0] == base[0] and "hop" not in two[0] and "relation_path" not in two[0]
    h1, h2 = two[1], two[2]
    assert h1["hop"] == 1 and h2["hop"] == 2
    assert [(e["kind"], e["dir"]) for e in h1["relation_path"]] == [("depends on", "out")]
    assert [(e["kind"], e["dir"]) for e in h2["relation_path"]] == [
        ("depends on", "out"),
        ("backed up by", "out"),
    ]
    assert h1["relation_path"][0]["to"] == h2["relation_path"][1]["from"]
    # the distance penalty: a hop fact never outranks a direct hit and deeper hops rank behind nearer ones
    assert h1["entity"] == "Ledger DB" and h2["entity"] == "Backup Vault"
    assert all(isinstance(r["score"], float) for r in two)


def test_relations_are_walked_in_both_directions(eng, world):
    got = eng.recall("Backup Vault retention", world["glob"], k=1, hops=2, **OFF)
    assert [r["entity"] for r in got] == ["Backup Vault", "Ledger DB", "Payment Service"]
    assert [e["dir"] for e in got[2]["relation_path"]] == ["in", "in"]


def test_only_current_facts_of_the_reached_entities_are_returned(eng, world):
    scope = world["glob"]
    eng.assert_fact("Ledger DB", "engine", "postgres seventeen", scope, "a1", now=30)  # supersedes sixteen
    got = eng.recall(QUERY, scope, k=1, hops=1, **OFF)
    assert "postgres seventeen" in _values(got) and "postgres sixteen" not in _values(got)


def test_relations_respect_scopes(eng, glob):
    p = eng.create_scope("project", "p", inherits=[glob])
    q = eng.create_scope("project", "q", inherits=[glob])
    eng.assert_fact("Payment Service", "latency", "p99 is 120 ms", glob, "a1", now=1)
    eng.assert_fact("Ledger DB", "engine", "postgres sixteen", glob, "a1", now=1)
    eng.assert_relation("Payment Service", "depends on", "Ledger DB", p, now=2)
    assert _values(eng.recall(QUERY, p, k=1, hops=1)) == ["p99 is 120 ms", "postgres sixteen"]
    assert _values(eng.recall(QUERY, q, k=1, hops=1)) == ["p99 is 120 ms"]  # the relation lives in p only
    assert _values(eng.recall(QUERY, glob, k=1, hops=1)) == [
        "p99 is 120 ms"
    ]  # and parents do not see children
    r = eng.create_scope("user", "r", inherits=[p])
    assert _values(eng.recall(QUERY, r, k=1, hops=1)) == [
        "p99 is 120 ms",
        "postgres sixteen",
    ]  # children inherit


def test_hops_are_bounded_per_hop(eng, glob):
    eng.assert_fact("Hub", "role", "the centre", glob, "a1", now=1)
    for i in range(30):
        eng.assert_fact(f"Leaf{i:02d}", "note", f"leaf value {i} about leaf{i:02d}", glob, "a1", now=2)
        eng.assert_relation("Hub", "links", f"Leaf{i:02d}", glob, now=3)
    got = eng.recall("Hub role centre", glob, k=1, hops=1, budget_chars=20_000)
    hop1 = [r for r in got if r.get("hop") == 1]
    assert len(got) == 1 + rel.HOP_FACTS and len(hop1) == rel.HOP_FACTS == 20
    # at most 3 facts per entity even when an entity has many
    for i in range(5):
        eng.assert_fact("Leaf00", f"extra{i}", f"more {i}", glob, "a1", now=4)
    again = eng.recall("Hub role centre", glob, k=1, hops=1, budget_chars=20_000)
    assert sum(1 for r in again if r["entity"] == "Leaf00") <= rel.HOP_FACTS_PER_ENTITY


def test_a_cycle_does_not_repeat_entities_or_facts(eng, glob):
    eng.assert_fact("A", "p", "alpha fact", glob, "a1", now=1)
    eng.assert_fact("B", "p", "beta fact", glob, "a1", now=1)
    eng.assert_fact("C", "p", "gamma fact", glob, "a1", now=1)
    eng.assert_relation("A", "next", "B", glob)
    eng.assert_relation("B", "next", "C", glob)
    eng.assert_relation("C", "next", "A", glob)
    got = eng.recall("A p alpha fact", glob, k=1, hops=2)
    ids = [r["fact_id"] for r in got]
    assert len(ids) == len(set(ids)) == 3


def test_hops_without_relations_or_hits_change_nothing(eng, glob):
    assert eng.recall("anything", glob, k=3, hops=2) == []
    eng.assert_fact("Solo", "p", "lonely fact", glob, "a1", now=1)
    assert eng.recall("Solo p lonely", glob, k=3, hops=2, **OFF) == eng.recall(
        "Solo p lonely", glob, k=3, **OFF
    )


def test_hops_must_be_0_1_or_2(eng, glob):
    for bad in (-1, 3):
        with pytest.raises(ValueError, match="hops"):
            eng.recall("x", glob, hops=bad)


def test_hops_zero_issues_no_extra_query(eng, world, client, monkeypatch):
    seen: list[str] = []
    real = client.ro

    def spy(graph, name, *a, **kw):
        seen.append(name)
        return real(graph, name, *a, **kw)

    monkeypatch.setattr(client, "ro", spy)
    eng.recall(QUERY, world["glob"], k=1, **OFF)
    plain = list(seen)
    seen.clear()
    eng.recall(QUERY, world["glob"], k=1, hops=0, **OFF)
    # the named entity's own facts join the candidates (CROSS_CHECK §3.3) through the recall_hop_facts
    # shape at hop 0; no relation is walked
    assert seen == plain and not any("relates" in n for n in seen)
    assert seen.count("engram/recall_hop_facts") == 1, "the §3.3 union read; the query names Payment Service"
    seen.clear()
    eng.recall(QUERY, world["glob"], k=1, hops=2, **OFF)
    assert seen.count("engram/relates_level") == 2 and seen.count("engram/recall_hop_facts") == 2


def test_hops_work_with_the_default_forgetting_rerank_too(eng, world):
    got = eng.recall(QUERY, world["glob"], k=1, hops=2)
    assert [r["entity"] for r in got] == ["Payment Service", "Ledger DB", "Backup Vault"]
    assert got[0]["activation"] is not None and got[1].get("hop") == 1


# -- plan shape: the hop queries follow the entity, not the scope ----------------------------------------


def test_plan_shape_hop_queries_do_not_enumerate_the_scope(client, graph):
    from tests.plan_util import BIG, max_records, profile_ops, seed_big_scope

    seed_big_scope(client, graph)  # 400 facts, 80 entities, one scope 'S'
    client.graph(graph).query(
        "UNWIND range(0, 78) AS i MATCH (a:Entity {id: 'E' + toString(i)}), "
        "(b:Entity {id: 'E' + toString(i + 1)}) "
        "CREATE (a)-[:RELATES {kind: 'next', scope_id: 'S', at: 1}]->(b)"
    )
    ops = profile_ops(
        client,
        graph,
        "engram/relates_level",
        {"frontier": ["E5"], "scope_id": "S", "all": False, "limit": 200},
    )
    assert max_records(ops).records < BIG // 10, str(max_records(ops))
    vec = client.graph(graph).ro_query("MATCH (f:Fact {id: 'F0'}) RETURN f.embedding").result_set[0][0]
    params = {
        "entity_ids": ["E6", "E4"],
        "scope_id": "S",
        "all": False,
        "t": 5,
        "statuses": ["active"],
        "per_entity": 3,
        "q": list(vec),
    }
    ops = profile_ops(client, graph, "engram/recall_hop_facts", params)
    assert max_records(ops).records < BIG // 10, "\n".join(map(str, ops))
    rows = client.ro(graph, "engram/recall_hop_facts", params)
    assert len(rows) == 6 and {r["entity_id"] for r in rows} == {"E4", "E6"}
    # P12: scope 'all' (OPTIONAL scope path) keeps the anchored plan and the same rows in a one-scope graph
    ops = profile_ops(client, graph, "engram/recall_hop_facts", {**params, "all": True})
    assert max_records(ops).records < BIG // 10, "\n".join(map(str, ops))
    assert len(client.ro(graph, "engram/recall_hop_facts", {**params, "all": True})) == 6
