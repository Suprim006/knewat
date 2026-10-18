from __future__ import annotations

import pytest

from knewat.embed import HashEmbedder
from knewat.engram import Engram
from knewat.lineage import Lineage
from knewat.relay import Relay


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


class World:
    """Mini-scenario with known answers, built through the real Engram / Relay / Lineage functions.

    time   who        step  what
    1000   researcher R1    asserts database=PostgreSQL 16 (source GOOD)           -> v1
    2000   researcher R2    asserts cache=Redis 7 (source BAD), session store derived from the cache fact
    2500   planner    P0    asserts language=Python 3.12 (no source)                -> other
    3000   planner    P1    recalls (every active fact is returned)
    4000   planner    P2    records decision D1 BASED_ON db v1 + cache
    5000   builder    B1    recalls only db v1
    6000   researcher R3    asserts database=PostgreSQL 17, which supersedes v1    -> v2
    7000   builder    B2    recalls only db v2
    """


@pytest.fixture
def world(eng, relay, lin, client, graph) -> World:
    w = World()
    w.eng, w.relay, w.lin, w.client, w.graph = eng, relay, lin, client, graph
    w.glob = eng.create_scope("global", "global", now=1)
    w.proj = eng.create_scope("project", "acme", inherits=[w.glob], now=1)
    for aid, role in (("researcher", "researcher"), ("planner", "planner"), ("builder", "builder")):
        relay.register_agent(aid, aid, role, "test")
    relay.create_tasks([{"id": "t-build", "title": "build the API"}])
    w.good = lin.create_source("https://docs.example/postgres", kind="url", now=1)
    w.bad = lin.create_source("https://blog.example/redis-tips", kind="url", trust=0.1, now=1)
    subject = "Acme Notes API"

    w.sess = eng.start_session("researcher", "researcher", now=900)
    w.ep = eng.remember_episode(w.sess, "user", "we use postgres", now=950)

    w.r1 = lin.record_step("researcher", 1, at=1000)
    r = eng.assert_fact(
        subject,
        "database",
        "PostgreSQL 16",
        w.proj,
        "researcher",
        source_id=w.good,
        episode_id=w.ep,
        now=1000,
    )
    w.db1 = r["fact_id"]
    lin.link_assert_result(w.r1, r)

    w.r2 = lin.record_step("researcher", 2, at=2000)
    r = eng.assert_fact(subject, "cache", "Redis 7", w.proj, "researcher", source_id=w.bad, now=2000)
    w.cache = r["fact_id"]
    lin.link_assert_result(w.r2, r)
    r = eng.assert_fact(subject, "session store", "Redis", w.proj, "researcher", now=2001)
    w.sessstore = r["fact_id"]
    lin.derive_from(w.sessstore, [w.cache])
    lin.link_assert_result(w.r2, r)

    w.p0 = lin.record_step("planner", 0, at=2500)
    r = eng.assert_fact(subject, "language", "Python 3.12", w.proj, "planner", now=2500)
    w.other = r["fact_id"]
    lin.link_assert_result(w.p0, r)

    w.p1 = lin.record_step("planner", 1, at=3000)
    w.q1 = "what does Acme use"
    w.results1 = eng.recall(w.q1, w.proj, k=8)
    w.recall1 = lin.record_recall("planner", w.p1, w.q1, w.proj, 8, w.results1, now=3000)

    w.p2 = lin.record_step("planner", 2, at=4000)
    w.decision = relay.record_decision(
        "planner", "t-build", "use postgres and redis", [w.db1, w.cache], now=4000
    )
    lin.link_step(w.p2, wrote_ids=[w.decision])

    w.b1 = lin.record_step("builder", 1, at=5000)
    w.results2 = [{"fact_id": w.db1, "score": 0.1}]
    w.recall2 = lin.record_recall("builder", w.b1, "database", w.proj, 1, w.results2, now=5000)

    w.r3 = lin.record_step("researcher", 3, at=6000)
    r = eng.assert_fact(
        subject, "database", "PostgreSQL 17", w.proj, "researcher", source_id=w.good, now=6000
    )
    assert r["superseded"] == [w.db1]
    w.db2 = r["fact_id"]
    lin.link_assert_result(w.r3, r)

    w.b2 = lin.record_step("builder", 2, at=7000)
    w.recall3 = lin.record_recall(
        "builder", w.b2, "database", w.proj, 1, [{"fact_id": w.db2, "score": 0.05}], now=7000
    )
    return w
