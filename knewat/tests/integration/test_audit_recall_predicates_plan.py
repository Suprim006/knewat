"""Audit B2: what ``engram/recall_predicates`` really reads on FalkorDB 6.0.2 with the production index set.

The audit feared the ``Fact.predicate`` seek returns every fact with that predicate "in all scopes, statuses
and times". Measured: the index scan applies ``predicate``, ``status`` (indexed) and ``valid_to`` (indexed)
together, so the superseded history and the expired facts are never read. What remains is the CURRENT facts
with that predicate in EVERY scope plus one ``IN_SCOPE`` hop each (the scope is an edge, so no
single-property index can absorb it). This test pins the first part so a dropped index or a rewritten filter
cannot bring the history back.
"""

from __future__ import annotations

import pytest
from tests.plan_util import OPEN, profile_ops

N_HIST = 1000  # superseded, predicate p, scope S
N_EXP = 500  # active but expired, predicate p, scope S
N_CUR = 100  # current, predicate p, scope S  (the fan)
N_OTHER = 300  # current, predicate p, scope OTHER (read, then dropped by the scope test)


@pytest.fixture
def history(client, graph):
    g = client.graph(graph)
    g.query(
        "CREATE (:Scope {id:'S', kind:'project', name:'s'}), (:Scope {id:'OTHER', kind:'project', name:'o'})"
    )  # noqa: E501

    def seed(prefix: str, n: int, scope: str, status: str, valid_to: int) -> None:
        for start in range(0, n, 500):
            g.query(
                """UNWIND range($a, $b) AS i MATCH (s:Scope {id: $scope})
                   CREATE (f:Fact {id: $p + toString(i), predicate: 'p', status: $status, valid_from: 1,
                                   valid_to: $vt})-[:IN_SCOPE]->(s)""",
                {
                    "a": start,
                    "b": min(start + 499, n - 1),
                    "scope": scope,
                    "status": status,
                    "vt": valid_to,
                    "p": prefix,
                },  # fmt: skip
            )

    seed("H", N_HIST, "S", "superseded", 2)
    seed("X", N_EXP, "S", "active", 3)
    seed("C", N_CUR, "S", "active", OPEN)
    seed("O", N_OTHER, "OTHER", "active", OPEN)
    return graph


PARAMS = {"predicates": ["p", "nope"], "scope_id": "S", "all": False, "statuses": ["active"], "t": 5}


def test_the_seek_excludes_history_and_expired_facts(client, history):
    ops = profile_ops(client, history, "engram/recall_predicates", PARAMS)
    scans = [op for op in ops if op.name == "Node By Index Scan" and "f:Fact" in op.args]
    assert scans, "\n".join(map(str, ops))
    read = max(op.records for op in scans)
    assert read <= N_CUR + N_OTHER, f"history / expired facts were read: {read}\n" + "\n".join(map(str, ops))
    assert read < N_HIST, "the predicate seek must not return the superseded history"


def test_rows_and_fan(client, history):
    rows = {r["predicate"]: r["fan"] for r in client.ro(history, "engram/recall_predicates", PARAMS)}
    assert rows == {"p": N_CUR, "nope": 0}
    # a missing scope gives one row per predicate with fan 0 (the header used to say "no rows")
    rows = client.ro(history, "engram/recall_predicates", {**PARAMS, "scope_id": "zzz"})
    assert sorted((r["predicate"], r["fan"]) for r in rows) == [("nope", 0), ("p", 0)]
