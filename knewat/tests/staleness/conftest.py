from __future__ import annotations

import pytest

from knewat.activation import Activation, Settings
from knewat.embed import HashEmbedder
from knewat.engram import Engram
from knewat.lineage import Lineage
from knewat.relay import Relay
from knewat.staleness import Staleness


class Clock:
    def __init__(self, start: int = 1_000_000):
        self.t = start

    def __call__(self) -> int:
        return self.t

    def advance(self, ms: int) -> int:
        self.t += ms
        return self.t


def cypher(client, graph, q: str, **params):
    """Ad-hoc read for assertions."""
    return client.graph(graph).ro_query(q, params or None).result_set


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def eng(client, graph) -> Engram:
    return Engram(client, graph, HashEmbedder())


@pytest.fixture
def lin(client, graph, clock) -> Lineage:
    return Lineage(client, graph, clock=clock)


@pytest.fixture
def relay(client, graph, clock) -> Relay:
    return Relay(client, graph, clock=clock)


@pytest.fixture
def stale(client, graph, eng, clock) -> Staleness:
    return Staleness(client, graph, engram=eng, clock=clock)


class Mem:
    """A tiny memory: one project scope, a helper to assert facts through the real Engram."""

    def __init__(self, eng, lin, relay, clock):
        self.eng, self.lin, self.relay, self.clock = eng, lin, relay, clock
        self.glob = eng.create_scope("global", "global", now=1)
        self.proj = eng.create_scope("project", "acme", inherits=[self.glob], now=1)
        relay.register_agent("alice", "alice", "builder", "test")
        relay.create_tasks([{"id": "t1", "title": "ship it"}])

    def fact(self, predicate: str, value: str, subject: str = "Payments", source_id=None, agent="alice"):
        r = self.eng.assert_fact(
            subject,
            predicate,
            value,
            self.proj,
            agent,
            source_id=source_id,
            now=self.clock.t,
            supersede=True,
        )
        return r["fact_id"]

    def source(self, uri: str, kind: str = "doc") -> str:
        return self.lin.create_source(uri, kind, now=self.clock.t)

    def decision(self, *fact_ids: str, text: str = "go with it") -> str:
        return self.relay.record_decision("alice", "t1", text, list(fact_ids), now=self.clock.t)


@pytest.fixture
def mem(eng, lin, relay, clock) -> Mem:
    return Mem(eng, lin, relay, clock)


LATER = 5_000_000_000_000  # far in the future: every fact is faint


@pytest.fixture
def act(client, graph, clock) -> Activation:
    return Activation(client, graph, Settings(), clock=clock)


def sweep_to_dormant(act, fid):
    out = act.sweep(scope_of(act, fid), threshold=50.0, dry_run=False, now=LATER)
    assert fid in out["moved"], out


def scope_of(act, fid):
    q = "MATCH (:Fact {id:$f})-[:IN_SCOPE]->(s:Scope) RETURN s.id"
    return cypher(act.client, act.graph, q, f=fid)[0][0]


def row(client, graph, fid):
    r = cypher(
        client,
        graph,
        "MATCH (f:Fact {id:$f}) RETURN f.status, f.valid_to, coalesce(f.verify_state,'verified'), "
        "coalesce(f.suspect_since,0)",
        f=fid,
    )
    return r[0]
