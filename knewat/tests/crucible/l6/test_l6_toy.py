"""L6 at toy size: the generators' truth, the loaders' counts, the scorer, and every deterministic arm against the truth.

No result is recorded here (the registered sizes are run by ``knewat.crucible.l6.run``). Cypher arms need a FalkorDB on
``KNEWAT_TEST_DB_PORT`` and are marked ``integration``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from knewat.crucible.l6 import arms_a as A
from knewat.crucible.l6 import arms_b as B
from knewat.crucible.l6 import arms_d as D
from knewat.crucible.l6 import score as SC
from knewat.crucible.l6 import stores as S
from knewat.crucible.l6 import world as W
from knewat.graph.client import GraphClient

DB_PORT = int(os.environ.get("KNEWAT_TEST_DB_PORT", "6310"))


@pytest.fixture(scope="module")
def wa():
    return W.gen_a(0.02)


@pytest.fixture(scope="module")
def wb():
    return W.gen_b(0.02)


@pytest.fixture(scope="module")
def wd():
    return W.gen_d(0.1)


def test_a_spec_covers_the_registered_grid():
    specs = [W.a_spec(i) for i in range(24)]
    assert {s[0] for s in specs} == set(W.BLAST_SIZES)
    assert {(b, d) for b, d in specs[:16]} >= {(1000, 12), (5000, 12), (5000, 2), (10, 2)}
    assert all(d <= b for b, d in specs)
    assert specs[12] == (10, 10)  # depth 12 does not fit in 10 facts: capped at the blast size


def test_a_truth_is_a_plain_bfs_over_the_ledger(wa):
    w, qs = wa
    ch = W.children_map(w)
    fidx = w.fact_index()
    assert len(qs) == 24
    for q in qs:
        blast = W.descendants(ch, q.source)
        assert len(blast) == q.answer["facts"] == q.blast
        assert q.answer == W.truth_a(w, blast, q.probes, fidx)
        assert sum(q.answer["probes"]) == min(5, q.blast) and len(q.probes) == 10
        ats = [fidx[i]["at"] for i in q.answer["earliest5"]]
        assert ats == sorted(ats)
    assert len({f["at"] for f in w.facts}) == len(w.facts)


def test_a_has_diamonds(wa):
    w, _ = wa
    multi = [f for f in w.facts if len(f["parents"]) > 1]
    assert len(multi) > 0.2 * len(w.facts)  # fan-in 2-3 is common, so the path count exceeds the node count


def test_generators_are_deterministic():
    assert W.gen_a(0.01)[0].facts == W.gen_a(0.01)[0].facts
    assert W.gen_b(0.01)[1][5].answer == W.gen_b(0.01)[1][5].answer


def test_b_chain_is_unique_and_twins_share_texts(wb):
    w, qs = wb
    assert [q.depth for q in qs] == [d for d in W.CHAIN_DEPTHS for _ in range(4)]
    fidx = w.fact_index()
    for q in qs:
        assert len(q.answer["chain"]) == q.depth
        twin = w.meta["twins"][str(q.chain_index)]
        assert [fidx[i]["text"] for i in twin["chain"]] == [fidx[i]["text"] for i in q.answer["chain"]]
        assert set(twin["chain"]).isdisjoint(q.answer["chain"])


def test_d_questions_are_unambiguous(wd):
    w, qs = wd
    assert len(qs) == 24 and w.meta["sprints"] >= 8
    assert {q.template for q in qs} == set(W.D_TEMPLATES)
    assert all(q.answer is not None for q in qs)


def test_dag_truth():
    w, q = W.gen_dag(8)
    assert q.answer["tasks"] == len(w.tasks) - 1 - 20
    assert sum(q.answer["probes"]) == 5


def test_scorer_strictness_and_forms():
    exp = {
        "facts": 3,
        "agents": 2,
        "decisions": 1,
        "handoffs": 0,
        "probes": [True, False],
        "earliest5": ["f1", "f2"],
    }
    got = {
        "facts": "3",
        "agents": 2,
        "decisions": 1,
        "handoffs": 0,
        "probes": ["yes", "no"],
        "earliest5": [" F1", "f2 "],
    }
    ok, comp = SC.score("A", exp, got)
    assert ok and all(comp.values())
    ok, comp = SC.score("A", exp, {**exp, "agents": 3})
    assert not ok and comp["agents"] is False and comp["facts"] is True
    assert SC.score("A", exp, "not an object")[0] is False
    assert SC.score("B", {"chain": ["a", "b"], "agent": "x"}, {"chain": ["b", "a"], "agent": "x"})[1] == {
        "chain": False,
        "agent": True,
    }
    assert SC.score("D", ["x", "y"], ["y", "x"], "shared_sources")[0] is True
    assert SC.score("D", ["S1", "S2", "S3"], ["S2", "S1", "S3"], "top_sprints")[0] is False


def test_sqlite_loader_counts_and_b1h_answers(wa, tmp_path: Path):
    w, qs = wa
    path, got = S.build_sqlite(w, tmp_path, "a")
    assert all(got[k] == v for k, v in w.counts().items() if k in got)
    arm = A.SqlArm(path)
    untuned = A.SqlArm(S.build_sqlite(w, tmp_path, "a2", tuned=False)[0], tuned=False)
    for q in qs:
        for a in (arm, untuned):
            ans, m = a.blast(q)
            assert not m["error"] and SC.score("A", q.answer, ans)[0], q.id
    assert arm.explain(qs[3])


def test_b1h_answers_family_b(wb, tmp_path: Path):
    w, qs = wb
    arm = B.SqlB(S.build_sqlite(w, tmp_path, "b")[0])
    for q in qs:
        ans, _ = arm.answer(q)
        assert SC.score("B", q.answer, ans)[0], q.id


def test_b1h_answers_family_d(wd, tmp_path: Path):
    w, qs = wd
    arm = D.SqlD(S.build_sqlite(w, tmp_path, "d")[0])
    for q in qs:
        ans, _ = arm.answer(q)
        assert SC.score("D", q.answer, ans, q.template)[0], (q.id, ans, q.answer)


def test_b1h_dag_and_the_union_all_trap(tmp_path: Path):
    w, q = W.gen_dag(8)
    arm = A.SqlArm(S.build_sqlite(w, tmp_path, "dag")[0])
    ans, _ = arm.dag(q)
    assert SC.score("dag", q.answer, ans)[0]
    ua, _ = arm.dag(q, union_all=True)
    assert ua["tasks"] == q.answer["tasks"]  # same count (DISTINCT), but the statement enumerates paths


def test_files_export(wa, tmp_path: Path):
    w, _ = wa
    counts = S.write_files(w, tmp_path / "f")
    assert counts["facts"] == len(w.facts)
    chunks = S.file_text_chunks(tmp_path / "f")
    assert sum(1 for n, _ in chunks if n == "facts.jsonl") == len(w.facts)


# -------------------------------------------------------------------------------------------- Cypher arms (need FalkorDB)
@pytest.fixture(scope="module")
def client():
    c = GraphClient(host="127.0.0.1", port=DB_PORT)
    yield c
    c.close()


@pytest.mark.integration
def test_cypher_arms_family_a_and_dag(wa, client):
    w, qs = wa
    name, _ = S.load_knewat(w, client, "l6_toy_a")
    try:
        g = client.graph(name)
        tuned, anchored = A.TunedArm(g), A.AnchoredArm(g)
        for q in qs:
            for arm in (tuned, anchored):
                ans, m = arm.blast(q)
                assert not m["error"] and SC.score("A", q.answer, ans)[0], (q.id, type(arm).__name__)
        ans, m = A.NaiveArm(g).blast(qs[0])
        assert m["error"] in (
            "",
            "timeout",
        )  # the natural form is planned from the Fact side: it may time out
        if not m["error"]:
            assert SC.score("A", qs[0].answer, ans)[0]
    finally:
        client.delete_graph(name)
    w, q = W.gen_dag(8)
    name, _ = S.load_knewat(w, client, "l6_toy_dag")
    try:
        g = client.graph(name)
        for arm in (A.TunedArm(g), A.NaiveArm(g)):
            ans, _ = arm.dag(q)
            assert SC.score("dag", q.answer, ans)[0]
    finally:
        client.delete_graph(name)


@pytest.mark.integration
def test_cypher_arms_family_b_and_d(wb, wd, client):
    w, qs = wb
    name, _ = S.load_knewat(w, client, "l6_toy_b")
    try:
        g = client.graph(name)
        for arm in (B.TunedB(g), B.NaiveB(g)):
            for q in qs:
                ans, m = arm.answer(q)
                assert SC.score("B", q.answer, ans)[0], (q.id, type(arm).__name__, m)
    finally:
        client.delete_graph(name)
    w, qs = wd
    name, _ = S.load_knewat(w, client, "l6_toy_d")
    try:
        arm = D.CypherD(client.graph(name))
        for q in qs:
            ans, _ = arm.answer(q)
            assert SC.score("D", q.answer, ans, q.template)[0], (q.id, ans, q.answer)
    finally:
        client.delete_graph(name)
