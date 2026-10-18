"""Relay fixtures: a Relay bound to a throwaway graph, with a controllable clock."""

from __future__ import annotations

import pytest

from plexus.relay import Relay


class Clock:
    """Deterministic epoch-ms clock; tests advance it explicitly."""

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
def relay(client, graph, clock) -> Relay:
    return Relay(client, graph, clock=clock)


def count(client, graph, cypher_name: str, params=None) -> int:
    return client.ro(graph, cypher_name, params)[0]["n"]
