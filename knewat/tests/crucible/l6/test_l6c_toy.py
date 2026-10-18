"""L6-C at toy size: generator invariants, both hand-written arms against the generator's truth, the product arm runs, plan shape.

No result is recorded here (the registered size is run by ``knewat.crucible.l6.run_c``). Needs a FalkorDB on
``KNEWAT_TEST_DB_PORT`` (marked ``integration``).
"""

from __future__ import annotations

import math
import os

import pytest

from knewat.crucible.l6 import arms_c as C
from knewat.crucible.l6 import stores_c as S
from knewat.crucible.l6 import world_c as W
from knewat.embed.hash_embedder import HashEmbedder
from knewat.engram.service import Engram
from knewat.graph.client import GraphClient

DB_PORT = int(os.environ.get("KNEWAT_TEST_DB_PORT", "6310"))
SCALE = 0.05


@pytest.fixture(scope="module")
def world():
    return W.generate(scale=SCALE)


@pytest.fixture(scope="module")
def client():
    c = GraphClient(host="127.0.0.1", port=DB_PORT)
    yield c
    c.close()


@pytest.fixture(scope="module")
def graph(world, client):
    name, _ = S.load_knewat_c(world, client, "l6c_toy_t")
    yield name
    client.delete_graph(name)


def test_generator_is_deterministic():
    a, b = W.generate(scale=0.03), W.generate(scale=0.03)
    assert a.facts == b.facts and a.relates == b.relates
    assert [q.expected_top5 for q in a.questions] == [q.expected_top5 for q in b.questions]


def test_world_shape(world):
    ents = world.entities
    assert len(ents) == 200 and len({e["name"] for e in ents}) == len(ents)
    a, b = set(W.WORDS_A), set(W.WORDS_B)
    assert len(a) >= 70 and len(b) >= 70 and not a & b and not (a | b) & set(W.PREDICATES)
    assert len(set(W.PREDICATES)) == 60 and all(
        len(w) >= 4 and w.islower() and w.isalpha() for w in W.PREDICATES
    )
    assert all(len(w) >= 3 for w in a | b)
    fans = world.fans()
    assert all(fans[e["id"]] == 120 for e in ents if e["hub"]) and sum(e["hub"] for e in ents) >= 2
    assert all(6 <= fans[e["id"]] <= 14 for e in ents if not e["hub"])
    per_entity: dict[str, list[str]] = {}
    for f in world.facts:
        per_entity.setdefault(f["entity_id"], []).append(f["predicate"])
        assert f["value"].startswith(f"{f['predicate']} of ") and len(f["value"].split()[-1]) == 6
    assert all(len(set(v)) == len(v) for e in ents if not e["hub"] for v in [per_entity[e["id"]]])
    keys = [(r["src"], r["dst"], r["kind"]) for r in world.relates]
    assert len(set(keys)) == len(keys) and all(s != d for s, d, _ in keys)


def test_questions_obey_the_rules(world):
    qs = world.questions
    for d in W.DEPTHS:
        assert sum(q.depth == d for q in qs) >= 3, d
    adj = world.adjacency()
    ln_fan = {k: math.log(v) for k, v in world.fans().items()}
    hub = {e["id"]: e["hub"] for e in world.entities}
    facts_of: dict[str, dict[str, list[str]]] = {}
    for f in world.facts:
        facts_of.setdefault(f["entity_id"], {}).setdefault(f["predicate"], []).append(f["id"])
    fact_entity = {f["id"]: f["entity_id"] for f in world.facts}
    for q in qs:
        best, dist = W.reach(adj, ln_fan, q.anchor_id, q.depth)
        cands = W.rank_candidates(best, facts_of, q.predicate)
        assert q.text == f"{q.anchor_name} {q.predicate}"
        assert [c[3] for c in cands[:5]] == q.expected_top5 and q.expected_top5[0] == q.answer_fact_id
        assert fact_entity[q.answer_fact_id] == q.answer_entity_id != q.anchor_id
        assert round(cands[1][0], 9) > round(cands[0][0], 9)  # the best candidate is unique on cost
        assert len({c[2] for c in cands if dist[c[2]] == q.depth}) >= 2
        assert dist[q.answer_entity_id] == q.depth
        for e, k in dist.items():  # nothing closer has the predicate (S1 exempts hubs)
            if k < q.depth and (q.stage == "S0" or not hub[e]):
                assert q.predicate not in facts_of.get(e, {}), (q.id, e)
        assert q.expected_top5 == W.truth(world, q.anchor_id, q.predicate, q.depth)
    assert world.meta["stage_counts"] and world.meta["cost_matters_share"]["all"] >= 0.0


def test_line_counts_are_positive():
    assert C.sql_lines() > 0 and C.cypher_lines() > 0


@pytest.mark.integration
def test_sql_and_tuned_cypher_match_the_truth(world, graph, client, tmp_path):
    paths = {t: S.build_sqlite_c(world, tmp_path / f"c_{t}.db", tuned=t)[0] for t in (True, False)}
    sql, sql_un, tuned = C.SqlC(paths[True]), C.SqlC(paths[False]), C.TunedC(client.graph(graph))
    for q in world.questions:
        a, ma = sql.answer(q)
        u, mu = sql_un.answer(q)
        c, mc = tuned.answer(q)
        assert not (ma["error"] or mu["error"] or mc["error"]), (q.id, ma, mu, mc)
        assert a["top5"] == q.expected_top5, (q.id, "B1h")
        assert u["top5"] == q.expected_top5, (q.id, "B1h-untuned")
        assert c["top5"] == q.expected_top5, (q.id, "P-tuned")
        assert a["top5"] == c["top5"] and a["fact"] == q.answer_fact_id
        assert (
            ma["statements"] == 1 and mc["statements"] >= 2
        )  # one CTE; hop statements + the facts statement


@pytest.mark.integration
def test_product_arm_runs(world, graph, client):
    for hops in (None, 0):
        arm = C.ProductC(Engram(C.RecordingClient(client), graph, HashEmbedder()), world.scope_id, hops)  # type: ignore[arg-type]
        for q in world.questions:
            ans, m = arm.answer(q)
            assert m["error"] == "", (q.id, hops, m)
            assert m["statements"] > 0 and isinstance(ans["top5"], list) and len(ans["top5"]) <= 5
            assert m.get("not_answerable", False) == (hops is None and q.depth > 2)


@pytest.mark.integration
def test_hop_statement_is_an_index_seek_not_a_relates_scan(world, graph, client):
    arm = C.TunedC(client.graph(graph))
    hub = next(e["id"] for e in world.entities if e["hub"])
    n_relates = len(world.relates)
    assert n_relates > 200

    def walk(op, acc):
        acc.append((op.name, str(op.args), op.profile_stats.records_produced if op.profile_stats else 0))
        for ch in op.children:
            walk(ch, acc)

    for frontier in ([world.entities[0]["id"]], [hub]):
        ops: list[tuple[str, str, int]] = []
        walk(arm.profile_hop(frontier).structured_plan, ops)
        seeks = [r for name, _, r in ops if name == "Node By Index Scan"]
        relates = [r for name, a, r in ops if "Traverse" in name and a.startswith(("(e)->", "(e)<-"))]
        assert seeks == [1, 1] and len(relates) == 2, (
            ops
        )  # one index seek per frontier id, one traversal per direction
        assert max(relates) < 50, ops  # the neighbours of ONE entity, not the RELATES edges of the graph
