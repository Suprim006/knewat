"""Forgetting + separation off (or as_of) is byte-identical to the retrieval order before P7-K.

D-013 added ``PLEXUS_RECALL_SEPARATION`` (on by default): with it on, the sibling expansion is fan-damped and
a query that names an entity is re-ranked, so the identity holds with BOTH switches off (the documented
contract).

``GOLDEN`` was captured by running ``golden_fixture.orders`` against main 4584219 (a ``git archive``
of the commit before any P7-K change), not against this branch.
"""

from __future__ import annotations

from typing import Any

import pytest

from . import golden_fixture
from .conftest import write

GOLDEN = [
    [
        [0.53709, ["Acme Notes API database: PostgreSQL 17"]],
        [0.714286, ["Acme Notes API auth: JWT bearer tokens", "Acme Notes API language: Python 3.12"]],
    ],
    [
        [0.552786, ["Billing Service database: MySQL 8", "Billing Service database: PostgreSQL 15"]],
        [0.591752, ["Acme Notes API database: PostgreSQL 17"]],
        [
            1.0,
            [
                "Acme Notes API auth: JWT bearer tokens",
                "Acme Notes API cache: Redis 7 with a 5 minute ttl",
                "Acme Notes API hosting: Docker on a single VM",
                "Acme Notes API language: Python 3.12",
                "Billing Service queue: RabbitMQ for invoice events",
            ],
        ],
    ],
    [
        # P12: before, "Acme Notes API hosting" ranked first only because zero-similarity Acme facts (distance
        # 1.0, tied) filled the k seeds in index order and boosted their sibling; such facts are no seeds now
        [0.795876, ["Web Frontend hosting: static files on a CDN"]],
        [0.80755, ["Acme Notes API hosting: Docker on a single VM"]],
        [
            1.0,
            [
                "Acme Notes API auth: JWT bearer tokens",
                "Acme Notes API cache: Redis 7 with a 5 minute ttl",
                "Acme Notes API language: Python 3.12",
            ],
        ],
    ],
    [
        [0.477767, ["Acme Notes API cache: Redis 7 with a 5 minute ttl"]],
        [0.741801, ["Search Index engine: Elasticsearch 8"]],
        [0.825922, ["Search Index reindex: nightly full reindex at 02:00"]],
        [1.0, ["Acme Notes API language: Python 3.12"]],
    ],
    [
        [0.666667, ["Acme Notes API hosting: Docker on a single VM"]],
        [0.795876, ["Acme Notes API database: PostgreSQL 17"]],
    ],
    [
        [0.345346, ["Web Frontend framework: React 18 with Vite"]],
        [0.795876, ["Web Frontend hosting: static files on a CDN"]],
        [
            1.0,
            [
                "Acme Notes API auth: JWT bearer tokens",
                "Acme Notes API cache: Redis 7 with a 5 minute ttl",
                "Acme Notes API hosting: Docker on a single VM",
                "Acme Notes API language: Python 3.12",
                "Billing Service database: MySQL 8",
                "Billing Service queue: RabbitMQ for invoice events",
            ],
        ],
    ],
]


def _cut_ties(orders: list[list[list[Any]]]) -> list[list[list[Any]]]:
    """The last group of each query is the tie at the k cut-off: WHICH tied facts make the cut is arbitrary
    (index return order before P12, fact id order since P12's larger candidate pool): only its size counts."""
    return [[*q[:-1], [q[-1][0], len(q[-1][1])]] if q else q for q in orders]


@pytest.fixture
def world(eng, scope):
    golden_fixture.build(eng, scope)
    return eng, scope


def test_forgetting_off_reproduces_the_pre_change_order(world):
    eng, scope = world
    assert _cut_ties(golden_fixture.orders(eng, scope, forgetting=False, separation=False)) == _cut_ties(
        GOLDEN
    )


def test_the_environment_switch_does_the_same(world, monkeypatch):
    eng, scope = world
    monkeypatch.setenv("PLEXUS_FORGETTING", "off")
    monkeypatch.setenv("PLEXUS_RECALL_SEPARATION", "off")
    assert _cut_ties(golden_fixture.orders(eng, scope)) == _cut_ties(GOLDEN)


def test_an_explicit_argument_beats_the_environment(world, monkeypatch):
    eng, scope = world
    monkeypatch.setenv("PLEXUS_FORGETTING", "off")
    rows = eng.recall("database", scope, k=3, forgetting=True)
    assert all(r["activation"] is not None for r in rows)
    monkeypatch.setenv("PLEXUS_FORGETTING", "on")
    rows = eng.recall("database", scope, k=3, forgetting=False)
    assert all(r["activation"] is None and r["protected"] is None for r in rows)


def test_as_of_mode_is_unaffected_by_forgetting(world, client, graph):
    eng, scope = world
    # age and boost some facts so that re-ranking WOULD change the order if it applied
    write(client, graph, "MATCH (f:Fact) WHERE f.value STARTS WITH 'PostgreSQL 1' SET f.surprise = 0.9")
    base = {
        q: golden_fixture.groups(eng.recall(q, scope, k=k, as_of=1_500, forgetting=False, separation=False))
        for q, k in golden_fixture.QUERIES
    }
    on = {
        q: golden_fixture.groups(eng.recall(q, scope, k=k, as_of=1_500, forgetting=True, separation=True))
        for q, k in golden_fixture.QUERIES
    }
    assert on == base
    assert all(
        r["activation"] is None for r in eng.recall("database", scope, k=3, as_of=1_500, forgetting=True)
    )
