"""P13 plan shape: the multi-source check reads the cascade's own facts, never the graph.

Each fact of the cascade reads its direct Source edges once (a pattern comprehension per fact in one CALL
subquery). A scan of every ``DERIVED_FROM`` edge or every Fact would show up as an operation producing about
as many records as the UNRELATED part of the graph holds. 200 cascade facts with two Sources each sit next to
1,500 unrelated facts; no operation may produce more than three records per cascade fact.
"""

from __future__ import annotations

import pytest

from plexus.graph.client import GraphClient

from ..plan_util import max_records, profile_ops
from .audit_util import OPEN, seed_scale

N = 200  # cascade facts
UNRELATED = 1500
BOUND = 3 * N  # an unrelated-edge scan would produce >= UNRELATED


def _seed(client: GraphClient, graph: str, *, second_quarantined: bool = False) -> None:
    seed_scale(client, graph, N)
    g = client.graph(graph)
    g.query("CREATE (:Source {id: 'SRC2', uri: 'u:src2', kind: 'doc', created_at: 1})")
    g.query("MATCH (s:Source {id: 'SRC2'}) MATCH (f:Fact) CREATE (f)-[:DERIVED_FROM]->(s)")
    if second_quarantined:
        g.query("MATCH (s:Source {id: 'SRC2'}) SET s.quarantined_at = 1")
    g.query("CREATE (:Source {id: 'OTHER', uri: 'u:o', kind: 'doc', created_at: 1})")
    g.query("CREATE (:Source {id: 'OTHER2', uri: 'u:o2', kind: 'doc', created_at: 1})")
    for lo in range(0, UNRELATED, 1000):
        rows = [{"i": i} for i in range(lo, min(lo + 1000, UNRELATED))]
        g.query(
            """UNWIND $rows AS r
               MATCH (a:Source {id: 'OTHER'}), (b:Source {id: 'OTHER2'})
               CREATE (f:Fact {id: 'U' + toString(r.i), status: 'active', valid_from: 1, valid_to: $open})
               CREATE (f)-[:DERIVED_FROM]->(a)
               CREATE (f)-[:DERIVED_FROM]->(b)""",
            {"rows": rows, "open": OPEN},
        )


QUARANTINE = {"source_id": "SRC", "now": 20_000, "limit": 5000, "depth": 8, "max_detail": 500}
FORGET = {**QUARANTINE, "reason": "r"}
RELEASE = {"source_id": "SRC", "limit": 5000, "depth": 8}


@pytest.mark.parametrize("second_quarantined", [False, True], ids=["corroborated", "all-hidden"])
def test_quarantine_reads_only_the_cascade(client, empty_graph, second_quarantined):
    _seed(client, empty_graph, second_quarantined=second_quarantined)
    ops = profile_ops(client, empty_graph, "lineage/quarantine", QUARANTINE)
    top = max_records(ops)
    assert top.records <= BOUND, str(top)


@pytest.mark.parametrize("second_quarantined", [False, True], ids=["unlinked", "quarantined-rest"])
def test_forget_reads_only_the_cascade(client, empty_graph, second_quarantined):
    _seed(client, empty_graph, second_quarantined=second_quarantined)
    ops = profile_ops(client, empty_graph, "lineage/forget_source", FORGET)
    top = max_records(ops)
    assert top.records <= BOUND, str(top)


def test_release_reads_only_the_cascade(client, empty_graph):
    _seed(client, empty_graph)
    client.rw(empty_graph, "lineage/quarantine", QUARANTINE)
    ops = profile_ops(client, empty_graph, "lineage/release_quarantine", RELEASE)
    top = max_records(ops)
    assert top.records <= BOUND, str(top)


def test_the_corroboration_check_is_one_call_subquery_not_a_carried_list_key(client):
    for name in ("lineage/quarantine", "lineage/forget_source"):
        text = client.library.get(name).statements[0]
        assert "WITH src, fs," not in text  # the fact list must never become a grouping key (audit P1)
        assert text.count("[(cx)-[:DERIVED_FROM]->(co:Source)") == 1
