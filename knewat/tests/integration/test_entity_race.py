"""P9-d: concurrent entity resolution (PRODUCT_FIXES_ANALYSIS C.4).

50 racers behind a barrier, each on its own connection, real bge-small vectors. Before
``engram/resolve_entity`` the lookups were separate reads followed by a MERGE on the *spelling*, so two
spellings of one thing created two Entities (verified in the analysis: 2 entities for a vector pair, 2 for
a full-text pair).
"""

from __future__ import annotations

import itertools
import random
import threading
from typing import Any

import pytest

from knewat.embed import FastEmbedder
from knewat.engram import Engram
from knewat.graph.client import GraphClient

pytestmark = pytest.mark.slow

RACERS = 50
RUNS = 20

# One thing, three ways to write it: B differs from A by punctuation (full-text hit, Jaccard 1.0), C by a
# plural (no shared token with A: only the embedding finds it; cosine distance 0.033 to A and 0.057 to B).
A, B, C = "Payment Service", "payment-service", "payment services"

PRODUCTS = """
Billing Kafka Grafana Redis Postgres Nginx Vault Consul Terraform Ansible
Jenkins Prometheus Elastic Rabbit Cassandra Mongo Snowflake Airflow Spark Flink
Istio Envoy Traefik Keycloak Sentry Datadog Splunk Jaeger Zipkin Loki
Argo Flux Helm Docker Podman Nomad Packer Pulumi Bazel Gradle
Webpack Vite Rollup Esbuild Parcel Deno Bun Hono Fastify Django
""".split()


@pytest.fixture(scope="module")
def fast() -> FastEmbedder:
    return FastEmbedder()


def _race(client, graph, embedder, calls: list[tuple[str, str]], *, seed: int = 0) -> list[dict[str, Any]]:
    """``resolve_entity_ex(name, kind)`` for every (name, kind) in ``calls`` at once, a connection each."""
    n = len(calls)
    clients = [
        GraphClient(host=client.host, port=client.port, password="", library=client.library) for _ in range(n)
    ]
    barrier = threading.Barrier(n)
    rng = random.Random(seed)
    delays = [rng.random() * 0.003 for _ in range(n)]  # shuffles who reaches the server first
    results: list[Any] = [None] * n
    errors: list[BaseException] = []

    def worker(i: int):
        try:
            eng = Engram(clients[i], graph, embedder)
            barrier.wait(timeout=60)
            threading.Event().wait(delays[i])
            results[i] = eng.resolve_entity_ex(calls[i][0], calls[i][1])
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        for c in clients:
            c.close()
    assert not errors, errors
    return results


def _entities(client, graph) -> list[list[Any]]:
    q = "MATCH (e:Entity) RETURN e.id, e.name ORDER BY e.created_at, e.id"
    return client.graph(graph).ro_query(q).result_set


@pytest.mark.parametrize("run", range(RUNS))
def test_50_racers_two_spellings_and_a_paraphrase_make_one_entity(client, graph, fast, run):
    calls = [(name, "service") for name in itertools.islice(itertools.cycle([A, B, C]), RACERS)]
    random.Random(run).shuffle(calls)
    results = _race(client, graph, fast, calls, seed=run)

    ents = _entities(client, graph)
    assert len(ents) == 1, ents
    assert {r["id"] for r in results} == {ents[0][0]}
    assert sum(r["created"] for r in results) == 1  # exactly one creator
    assert sum(r["matched_by"] == "new" for r in results) == 1


def test_the_paraphrase_alone_still_resolves_by_vector(client, graph, fast):
    """Guards the test above: C must reach A/B through the vector index, not by luck."""
    eng = Engram(client, graph, fast)
    a = eng.resolve_entity_ex(A, "service")
    assert eng.resolve_entity_ex(B, "service")["matched_by"] == "fulltext"
    c = eng.resolve_entity_ex(C, "service")
    assert (c["id"], c["matched_by"]) == (a["id"], "vector")


@pytest.mark.parametrize("run", range(5))
def test_50_racers_with_50_distinct_names_make_50_entities(client, graph, fast, run):
    names = list(PRODUCTS)
    assert len(set(names)) == RACERS
    random.Random(run).shuffle(names)
    results = _race(client, graph, fast, [(n, "service") for n in names], seed=run)
    assert len(_entities(client, graph)) == RACERS
    assert len({r["id"] for r in results}) == RACERS
    assert all(r["created"] and r["matched_by"] == "new" for r in results)


def test_50_numbered_names_stay_50_entities(client, graph, fast):
    """The numeric guard under race: 'Worker 1' .. 'Worker 50' differ only in a number and must not merge."""
    names = [f"Worker {i}" for i in range(RACERS)]
    results = _race(client, graph, fast, [(n, "service") for n in names])
    assert len(_entities(client, graph)) == RACERS
    assert len({r["id"] for r in results}) == RACERS


def test_service_1_and_service_2_racing_make_two_entities(client, graph, fast):
    calls = [("Service 1", "service"), ("service-2", "service")] * 25
    results = _race(client, graph, fast, calls)
    assert len(_entities(client, graph)) == 2
    assert len({r["id"] for r in results}) == 2


def test_same_name_in_two_kinds_races_to_one_entity(client, graph, fast):
    """norm_name is the entity key whatever the kind (UNIQUE backstop): racing kinds still gives one node."""
    calls = [("Redis", "tech"), ("redis", "service")] * 25
    results = _race(client, graph, fast, calls)
    assert len(_entities(client, graph)) == 1
    assert len({r["id"] for r in results}) == 1


# -- not transitive, but deterministic ------------------------------------------------------------------

X, Y, Z = "alpha beta gamma delta", "alpha beta gamma", "beta gamma"  # Y~X (3/4), Z~Y (2/3), Z!~X (2/4)
# What each arrival order produces, from the statement's rules: a name joins the best (then oldest) match.
EXPECTED_BY_ORDER = {
    (X, Y, Z): 2,  # Y joins X; Z vs X is 0.5 -> new
    (X, Z, Y): 2,  # Z new; Y joins X (3/4 beats Z's 2/3)
    (Y, X, Z): 1,  # X joins Y; Z joins Y
    (Y, Z, X): 1,  # Z joins Y; X joins Y
    (Z, Y, X): 2,  # Y joins Z; X vs Z is 0.5 -> new
    (Z, X, Y): 2,  # X new (0.5 vs Z); Y: X 3/4 beats Z 2/3 -> joins X
}


@pytest.mark.parametrize("order", list(EXPECTED_BY_ORDER))
def test_non_transitive_chain_is_deterministic_for_a_given_arrival_order(client, graph, fast, order):
    eng = Engram(client, graph, fast)
    ids = [eng.resolve_entity_ex(name, "thing")["id"] for name in order]
    assert len(set(ids)) == EXPECTED_BY_ORDER[order]


def test_non_transitive_chain_racing_yields_at_most_two(client, graph, fast):
    """Transitivity is not claimed: racing X, Y, Z gives 1 or 2 entities depending on arrival, never 3."""
    calls = [(n, "thing") for n in (X, Y, Z) * 17][:RACERS]
    results = _race(client, graph, fast, calls)
    n = len(_entities(client, graph))
    assert n in (1, 2)
    assert len({r["id"] for r in results}) == n


# -- the reason it matters: facts about two spellings meet ------------------------------------------------


def test_facts_about_two_spellings_land_on_one_entity_and_dedupe(client, graph, fast):
    eng = Engram(client, graph, fast)
    glob = eng.create_scope("global", "global")
    proj = eng.create_scope("project", "acme", inherits=[glob])
    r1 = eng.assert_fact(A, "database", "PostgreSQL 16", proj, "a1", now=1000, subject_kind="service")
    r2 = eng.assert_fact(B, "database", "PostgreSQL 16", proj, "a2", now=2000, subject_kind="service")
    r3 = eng.assert_fact(C, "database", "MySQL 8", proj, "a1", now=3000, subject_kind="service")
    assert r1["entity_id"] == r2["entity_id"] == r3["entity_id"]
    assert r2["duplicate_of"] == r1["fact_id"]
    assert r1["fact_id"] in r3["superseded"] + r3["contradicts"]  # the classification now sees the old fact
