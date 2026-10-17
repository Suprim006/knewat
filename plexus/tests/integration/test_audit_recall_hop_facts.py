"""Audit C2: ``engram/recall_hop_facts`` must return a fact once even when the searched scope reaches the
fact's scope over two INHERITS paths (a diamond: team -> org directly and team -> proj -> org).

Before the fix the post-DISTINCT ``MATCH (:Scope {id:$scope_id})-[:INHERITS*0..3]->(gs)`` emitted one row
per path, so the org fact filled two of the ``per_entity`` slots and the nearer proj/team facts were crowded
out.
"""

from __future__ import annotations

import random

import pytest
from tests.plan_util import OPEN, unit_vec

Q = unit_vec(random.Random(1))


def _emb(dist: float) -> list[float]:
    """A unit vector at a chosen cosine distance from ``Q`` (0 = identical)."""
    other = unit_vec(random.Random(2))
    # Gram-Schmidt: a unit vector orthogonal to Q
    dot = sum(a * b for a, b in zip(Q, other, strict=True))
    orth = [b - dot * a for a, b in zip(Q, other, strict=True)]
    n = sum(x * x for x in orth) ** 0.5
    orth = [x / n for x in orth]
    cos = 1.0 - dist
    sin = (1.0 - cos * cos) ** 0.5
    return [cos * a + sin * b for a, b in zip(Q, orth, strict=True)]


@pytest.fixture
def diamond(client, graph):
    g = client.graph(graph)
    g.query(
        """
        CREATE (org:Scope {id:'org', kind:'org', name:'org', created_at: 1}),
               (proj:Scope {id:'proj', kind:'project', name:'proj', created_at: 1}),
               (team:Scope {id:'team', kind:'team', name:'team', created_at: 1}),
               (team)-[:INHERITS]->(org), (team)-[:INHERITS]->(proj), (proj)-[:INHERITS]->(org),
               (e:Entity {id:'e1', name:'thing', norm_name:'thing'}), (a:Agent {id:'a1'})
        """
    )
    rows = [
        {"id": "g1", "sc": "org", "emb": _emb(0.10)},  # nearest, in the diamond's far corner
        {"id": "p1", "sc": "proj", "emb": _emb(0.20)},
        {"id": "t1", "sc": "team", "emb": _emb(0.30)},
    ]
    g.query(
        """
        UNWIND $rows AS r
        MATCH (e:Entity {id:'e1'}), (s:Scope {id: r.sc}), (a:Agent {id:'a1'})
        CREATE (f:Fact {id: r.id, subject_id: 'e1', predicate: 'p', value: r.id, norm_value: r.id,
                        value_tokens: '',
                        valid_from: 1, valid_to: $open, recorded_at: 1, created_at: 1, status: 'active',
                        confidence: 1.0, embedding: vecf32(r.emb), value_embedding: vecf32(r.emb)})
        CREATE (f)-[:ABOUT]->(e), (f)-[:IN_SCOPE]->(s), (f)-[:ASSERTED_BY {at: 1}]->(a)
        """,
        {"rows": rows, "open": OPEN},
    )
    return graph


def _hop(client, graph, per_entity: int) -> list[str]:
    rows = client.ro(
        graph,
        "engram/recall_hop_facts",
        {
            "entity_ids": ["e1"],
            "scope_id": "team",
            "t": 5,
            "statuses": ["active"],
            "per_entity": per_entity,
            "q": Q,
        },
    )
    return [r["fact_id"] for r in rows]


def test_a_fact_reachable_over_two_inherits_paths_is_returned_once(client, diamond):
    assert _hop(client, diamond, 10) == ["g1", "p1", "t1"]


def test_duplicates_do_not_fill_the_per_entity_slots(client, diamond):
    assert _hop(client, diamond, 2) == ["g1", "p1"], "before C2: ['g1', 'g1'] (p1 crowded out)"


def test_scope_filter_still_applies(client, diamond):
    rows = client.ro(
        diamond,
        "engram/recall_hop_facts",
        {"entity_ids": ["e1"], "scope_id": "proj", "t": 5, "statuses": ["active"], "per_entity": 10, "q": Q},
    )
    assert [r["fact_id"] for r in rows] == ["g1", "p1"], "team is not visible from proj"
