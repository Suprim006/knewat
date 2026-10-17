"""D-013 P1: pattern separation at recall against a real FalkorDB.

The embedder puts a fact at an exact cosine distance from the query: a value containing ``~0.30`` is 0.30
away from any text containing ``QUERY``, so relevance is exact and only the entity lift can change the order.
The query text also names the entity ("Acme Notes API S07 ... QUERY"), which is what the entity read resolves.
Every fact carries a marker: with dozens of hashed (exactly orthogonal) vectors the HNSW index failed to
navigate to the two nearest nodes at all (an artefact of the degenerate test space, seen while writing this).
"""

from __future__ import annotations

import hashlib
import math
import re

import pytest
from tests.plan_util import BIG, max_records, profile_ops, seed_big_scope

from plexus.activation import Activation, Settings
from plexus.embed import HashEmbedder
from plexus.embed.base import DIM
from plexus.engram import Engram
from plexus.lineage import Lineage

_MARK = re.compile(r"~(\d+\.\d+)")


class NamingEmbedder:
    """``QUERY`` in the text -> e0; ``~d`` -> a unit vector at cosine distance d from e0; else hashed."""

    def __init__(self) -> None:
        self.dim = DIM
        self._h = HashEmbedder()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        if "QUERY" in text:
            return [1.0] + [0.0] * (DIM - 1)
        m = _MARK.search(text)
        if not m:
            return self._h.embed([text])[0]
        cos = 1.0 - float(m.group(1))
        j = 1 + int.from_bytes(hashlib.md5(text.encode(), usedforsecurity=False).digest()[:4], "little") % (
            DIM - 1
        )
        v = [0.0] * DIM
        v[0], v[j] = cos, math.sqrt(max(0.0, 1.0 - cos * cos))
        return v


@pytest.fixture
def eng(client, graph) -> Engram:
    return Engram(client, graph, NamingEmbedder())


@pytest.fixture
def scope(eng) -> str:
    return eng.create_scope("global", "global", now=1)


def ids(rows):
    return [r["fact_id"] for r in rows]


@pytest.fixture
def twins(eng, scope):
    """S07 target at 0.30, its S08 twin NEARER at 0.29, and one sibling (another predicate, 0.40) each."""
    target = eng.assert_fact("Acme Notes API S07", "api_version", "v14 ~0.30", scope, "alice", now=1000)[
        "fact_id"
    ]
    twin = eng.assert_fact("Acme Notes API S08", "api_version", "v16 ~0.29", scope, "alice", now=1001)[
        "fact_id"
    ]
    sib = eng.assert_fact("Acme Notes API S07", "database", "pg ~0.40", scope, "alice", now=1002)["fact_id"]
    sib8 = eng.assert_fact("Acme Notes API S08", "database", "my ~0.40", scope, "alice", now=1003)["fact_id"]
    return target, twin, sib, sib8


Q = "Acme Notes API S07 api_version QUERY"


def test_the_named_entity_wins_over_a_nearer_twin_and_both_switches_off_keep_the_plain_order(
    eng, scope, twins
):
    target, twin, sib, sib8 = twins
    plain = eng.recall(Q, scope, k=4, forgetting=False, separation=False)
    assert ids(plain)[:2] == [twin, target], "nearer wins; both get the same sibling boost"
    assert all(r["entity_match"] is None and r["sep"] is None and r["lures"] == [] for r in plain)
    got, meta = eng.recall_with_meta(Q, scope, k=3, forgetting=False, separation=True)
    assert ids(got) == [target, twin, sib], (
        "the named entity's fact first; its sibling lifted above the twin's"
    )
    assert list(meta["entities"]) and all(
        e["name"] == "Acme Notes API S07" for e in meta["entities"].values()
    )
    e = next(iter(meta["entities"].values()))
    assert e["fan"] == 2, "two current facts about S07 in the scope"
    by = {r["fact_id"]: r for r in got}
    assert by[target]["entity_match"] is True and by[target]["sep"] == pytest.approx(
        0.15 * (1 - math.log(2) / math.log(50))
    )
    assert by[twin]["entity_match"] is False and by[twin]["sep"] == 0.0
    assert by[target]["lures"] == [twin] and by[twin]["lures"] == [target], (
        "same predicate, other entity, 0.01 apart"
    )
    assert by[sib]["lures"] == [sib8]


def test_the_twin_is_not_resolved_as_a_named_entity(eng, scope, twins):
    ents = eng._resolve_entities(Q, scope, 10_000, ["active"])
    assert [e["name"] for e in ents.values()] == ["Acme Notes API S07"]
    assert eng._resolve_entities("api_version QUERY", scope, 10_000, ["active"]) == {}
    # the exact norm_name pass finds an entity whose words the full-text OR also returns
    ents = eng._resolve_entities("acme   notes API s08", scope, 10_000, ["active"])
    assert [e["name"] for e in ents.values()] == ["Acme Notes API S08"] and next(iter(ents.values()))[
        "fan"
    ] == 2


def test_separation_works_with_forgetting_on_in_both_modes(eng, scope, twins):
    target, twin, sib, sib8 = twins
    for mode in ("mult", "add"):
        got = eng.recall(Q, scope, k=3, settings=Settings(act_mode=mode), forgetting=True, separation=True)
        assert ids(got)[0] == target, mode
        assert got[0]["activation"] is not None and got[0]["salience"] == 0.0


def test_a_hub_entity_gets_no_lift(eng, scope):
    for i in range(50):
        eng.assert_fact("Hub Service", f"setting_{i}", f"value {i} ~0.90", scope, "alice", now=1000 + i)
    target = eng.assert_fact("Hub Service", "api_version", "v1 ~0.30", scope, "alice", now=2000)["fact_id"]
    twin = eng.assert_fact("Other Service", "api_version", "v2 ~0.29", scope, "alice", now=2001)["fact_id"]
    got, meta = eng.recall_with_meta("Hub Service api_version QUERY", scope, k=2, forgetting=False)
    assert next(iter(meta["entities"].values()))["fan"] == 51
    assert ids(got) == [twin, target], "fan >= 50: relevance decides"
    assert got[1]["entity_match"] is True and got[1]["sep"] == 0.0


def test_why_recalled_stores_the_entities_the_separation_flag_and_the_lift(eng, scope, twins, client, graph):
    target, twin, sib, sib8 = twins
    hits, meta = eng.recall_with_meta(Q, scope, k=3, forgetting=False)
    lin = Lineage(client, graph)
    rid = lin.record_recall(
        "alice", None, Q, scope, 3, hits, entities=sorted(meta["entities"]), separation=True
    )
    why = lin.why_recalled(rid)
    assert why["recall"]["separation"] is True and why["recall"]["entities"] == sorted(meta["entities"])
    seps = {r["fact_id"]: r["sep"] for r in why["results"]}
    assert seps[target] > 0 and seps[twin] == 0.0
    edge = next(e for e in why["edges"] if e["rel"] == "RETURNED" and e["to"] == target)
    assert edge["props"]["sep"] == pytest.approx(seps[target])
    # a recall recorded without the D-013 arguments reads back with the defaults
    rid0 = lin.record_recall("alice", None, "q", scope, 1, [{"fact_id": target}])
    w0 = lin.why_recalled(rid0)
    assert (
        w0["recall"]["separation"] is False
        and w0["recall"]["entities"] == []
        and w0["results"][0]["sep"] == 0.0
    )


def test_memory_strength_reports_salience_fan_and_entity_lift(eng, scope, twins, client, graph):
    target, _, _, _ = twins
    s = Activation(client, graph, Settings(act_mode="add")).strength(target)
    assert s is not None
    assert (
        s["mode"] == "add"
        and s["fan"] == 2
        and s["entity_lift"] == pytest.approx(0.15 * (1 - math.log(2) / math.log(50)))
    )
    assert s["salience"] == 0.0 and s["suggested_verify_after"] is None and -0.05 <= s["act_term"] <= 0.05
    assert s["decays"] and all(0 < d <= 1.0 for d in s["decays"])


# -- plan shape: the entity read must not enumerate the scope ------------------------------------------


def test_recall_entities_is_an_index_seek_not_a_scope_scan(client, graph):
    seed_big_scope(client, graph)
    params = {"q": "e1|entity", "scope_id": "S", "limit": 5, "statuses": ["active"], "t": 5}
    ops = profile_ops(client, graph, "engram/recall_entities", params)
    worst = max_records(ops)
    assert worst.records < BIG, f"scope-wide enumeration: {worst}\n" + "\n".join(map(str, ops))
