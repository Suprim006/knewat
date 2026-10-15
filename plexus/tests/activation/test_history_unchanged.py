"""Slice 6: forgetting changes no history. A dormant fact (or a low activation) never hides a fact from the
time-travel and provenance tools, and a lookup by id still finds it."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from plexus.activation import Activation, Settings
from plexus.activation.model import DAY_MS

from .conftest import write

NOW = 5_000 * DAY_MS
OLD = NOW - 400 * DAY_MS


@pytest.fixture
def act(client, graph) -> Activation:
    return Activation(client, graph, Settings(), clock=lambda: NOW)


@pytest.fixture
def w(eng, relay, lin, scope, act, client, graph):
    """alice's database fact (400 days old, never used), read once by bob at step 1; then swept to dormant."""

    w = SimpleNamespace()
    relay.register_agent("alice", "alice", "x", "t")
    w.fact = eng.assert_fact("API", "database", "PostgreSQL 16", scope, "alice", now=OLD)["fact_id"]
    write(client, graph, "MATCH (f:Fact {id:$f}) SET f.surprise = 0.0", f=w.fact)
    w.step = lin.record_step("bob", 1, at=OLD + DAY_MS)
    w.recall_id = lin.record_recall(
        "bob", w.step, "database", scope, 3, [{"fact_id": w.fact}], now=OLD + DAY_MS
    )
    w.scope, w.act, w.lin, w.eng = scope, act, lin, eng
    return w


def snapshot(w) -> dict:
    """Everything the history tools say about the fact, with the (expected) status field removed."""
    hist = [
        {k: v for k, v in h.items() if k != "status"} for h in w.eng.fact_history("API", "database", w.scope)
    ]
    as_of = w.lin.as_of("API", "database", OLD + 2 * DAY_MS, w.scope)
    who = w.lin.who_knew(w.fact)
    knew = w.lin.knew_at("bob", 1)
    why = w.lin.why(w.fact)
    why_recalled = w.lin.why_recalled(w.recall_id)
    return {
        "history": hist,
        "as_of": None if as_of is None else {k: v for k, v in as_of.items() if k != "status"},
        "who": who,
        "knew": [{k: v for k, v in f.items() if k != "status"} for f in knew["facts"]],
        "why_root": why["root"],
        "why_recalled": [r["fact_id"] for r in why_recalled["results"]],
    }


def test_a_dormant_fact_is_still_answered_by_every_history_tool(w, client, graph):
    before = snapshot(w)
    assert before["as_of"] is not None and before["knew"] and before["why_recalled"] == [w.fact]
    moved = w.act.sweep(w.scope, dry_run=False)["moved"]
    assert moved == [w.fact]
    assert client.graph(graph).ro_query(
        "MATCH (f:Fact {id:$f}) RETURN f.status", {"f": w.fact}
    ).result_set == [["dormant"]]
    after = snapshot(w)
    assert after == before


def test_the_statuses_the_history_tools_report_say_dormant_not_gone(w):
    w.act.sweep(w.scope, dry_run=False)
    assert [h["status"] for h in w.eng.fact_history("API", "database", w.scope)] == ["dormant"]
    assert w.lin.as_of("API", "database", OLD + 2 * DAY_MS, w.scope)["status"] == "dormant"
    assert w.lin.knew_at("bob", 1)["facts"][0]["status"] == "dormant"


def test_lookups_by_id_ignore_activation_and_status(w, client, graph):
    w.act.sweep(w.scope, dry_run=False)
    assert w.lin.why(w.fact)["root"] == w.fact
    assert w.lin.who_knew(w.fact)["fact_id"] == w.fact
    row = client.ro(graph, "lineage/node_info", {"ids": [w.fact]})
    assert row and row[0]["id"] == w.fact


def test_reading_and_ranking_never_change_history(w, client, graph):
    before = snapshot(w)
    for _ in range(3):  # many recalls with forgetting on change activation only
        w.eng.recall("database", w.scope, k=5, forgetting=True)
    w.act.strength(w.fact)
    assert snapshot(w) == before


def test_as_of_recall_includes_dormant_facts(w):
    w.act.sweep(w.scope, dry_run=False)
    assert [h["fact_id"] for h in w.eng.recall("database", w.scope, k=5)] == []
    assert w.fact in [h["fact_id"] for h in w.eng.recall("database", w.scope, k=5, as_of=OLD + 2 * DAY_MS)]
