from __future__ import annotations

import pytest

from plexus.embed import HashEmbedder
from plexus.engram import Engram
from plexus.lineage import Lineage
from plexus.relay import Relay


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


def cypher(client, graph, q: str, **params):
    """Ad-hoc read for assertions."""
    return client.graph(graph).ro_query(q, params or None).result_set
