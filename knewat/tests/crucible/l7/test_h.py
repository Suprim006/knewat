"""Family H (L7): ground truth sanity and a toy end-to-end run of every Cypher/SQL arm (FalkorDB on KNEWAT_TEST_DB_PORT)."""

from __future__ import annotations

import pytest

from knewat.crucible.l7 import h
from knewat.crucible.l7.common import code_lines
from knewat.crucible.l7.h_world import SCALES, Truth, h_world

# arms that are expected to be wrong at toy size, by construction (reported as such in the results)
KNOWN_WRONG = {"H3:cypher:h3.shortestpath.cypher", "H1c:cypher:h1c.natural.cypher"}


def test_world_is_deterministic_and_plants_motifs():
    a, b = h_world("toy"), h_world("toy")
    assert a.facts == b.facts and a.fact_parents == b.fact_parents and a.handoffs == b.handoffs
    t = Truth(a)
    assert t.h1a()["count"] >= SCALES["toy"]["triangles"] - 1  # planted (a duplicate draw may coincide)
    assert t.h1b()["count"] >= 1
    kinds = {p["kind"]: [] for p in a.h3_pairs}
    for p in a.h3_pairs:
        kinds[p["kind"]].append((t.h3(p["a"], p["b"]), t.h3(p["a"], p["b"], constrained=False)))
    assert all(c == u and c is not None for c, u in kinds["plain"])
    assert all(c is not None and u is not None and c > u for c, u in kinds["trap"])
    assert all(c is None and u is not None for c, u in kinds["none"])


def test_truth_closure_and_derives_agree():
    w = h_world("toy")
    t = Truth(w)
    f = w.facts[-1]["id"]
    for x in t.closure([f]) - {f}:
        assert t.derives(f, x)


def test_query_files_are_counted():
    assert code_lines(h.qtext("h1a.cypher")) == 5
    assert h.unbounded_cypher(h.qtext("h3.varlen.cypher")).count("*1..]") == 1
    assert "r.depth < 8" not in h.unbounded_sql(h.qtext("h3.path_cte.sql"))
    assert h.BFS_LINES > 5


@pytest.mark.integration
def test_toy_run_every_arm(client, tmp_path):
    res = h.run_scale("toy", client.host, client.port, tmp_path, lambda m: None)
    by = {a["arm"]: a for a in res["arms"]}
    assert len(by) == 21
    for name, a in by.items():
        if name in KNOWN_WRONG:
            continue
        assert a["strict_correct"] == a["n"], (name, [q for q in a["questions"] if not q["strict"]][:2])
    assert by["H3:cypher:h3.shortestpath.cypher"]["strict_correct"] == 8  # wrong on exactly the 4 traps
