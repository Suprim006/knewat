"""Activation fixtures: Engram / Relay / Lineage on a throwaway graph, with a controllable clock."""

from __future__ import annotations

import pytest

from knewat.embed import HashEmbedder
from knewat.engram import Engram
from knewat.lineage import Lineage
from knewat.relay import Relay

DAY = 86_400_000
HOUR = 3_600_000


class Clock:
    def __init__(self, start: int = 1_000_000):
        self.t = start

    def __call__(self) -> int:
        return self.t

    def advance(self, ms: int) -> int:
        self.t += ms
        return self.t


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def eng(client, graph) -> Engram:
    return Engram(client, graph, HashEmbedder())


@pytest.fixture
def relay(client, graph, clock) -> Relay:
    return Relay(client, graph, clock=clock)


@pytest.fixture
def lin(client, graph, clock) -> Lineage:
    return Lineage(client, graph, clock=clock)


@pytest.fixture
def scope(eng) -> str:
    return eng.create_scope("global", "global", now=1)


def cypher(client, graph, q: str, **params):
    """Ad-hoc read for assertions."""
    return client.graph(graph).ro_query(q, params or None).result_set


def write(client, graph, q: str, **params):
    """Ad-hoc write for fixtures (hand-made edges the other P7 agent will create for real)."""
    return client.graph(graph).query(q, params or None).result_set


def reads(client, graph, step_id: str, fact_id: str):
    """``[[via, at]]`` of the READ edge(s) from a step to a fact."""
    return cypher(
        client,
        graph,
        "MATCH (:Step {id:$s})-[r:READ]->(:Fact {id:$f}) RETURN r.via, r.at",
        s=step_id,
        f=fact_id,
    )
