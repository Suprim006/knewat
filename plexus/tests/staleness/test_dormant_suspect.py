"""FIX-P7 P7-01: ``mark_changed`` must see ``dormant`` facts.

A sweep moves a fact to ``dormant`` (hidden from recall, reversible); a code change must still make it
suspect, so a restored fact carries its doubt.
"""

from __future__ import annotations

from .conftest import row, sweep_to_dormant

P = "C:/repo/app/payments.py"


# -- P7-01 ----------------------------------------------------------------------------------------------
def test_a_dormant_fact_becomes_suspect_when_its_code_changes(stale, mem, act, eng, client, graph, clock):
    f = mem.fact("timeout", "30 seconds")
    stale.anchor_fact(f, P)
    stale.mark_changed([{"path": P, "new_hash": "h0"}])
    sweep_to_dormant(act, f)
    assert row(client, graph, f)[0] == "dormant"

    clock.t = 2_000_000
    out = stale.mark_changed([{"path": P, "new_hash": "h1"}], commit="c1")
    assert out["changed"] == 1
    status, _, state, since = row(client, graph, f)
    assert (status, state, since) == ("dormant", "suspect", 2_000_000)  # still dormant, but doubted
    # hidden from the work list while dormant (it is not current), and reported only for active facts
    assert stale.facts_to_verify() == [] and out["suspect_fact_ids"] == []

    assert act.restore(f)["restored"] is True
    rows = stale.facts_to_verify()
    assert [r["fact_id"] for r in rows] == [f]
    hit = next(r for r in eng.recall("timeout", mem.proj) if r["fact_id"] == f)
    assert hit["verify_state"] == "suspect"
    assert hit["suspect_reason"] == "changed in c1 (C:/repo/app/payments.py)"


def test_a_dormant_fact_derived_from_a_changed_source_becomes_suspect(stale, mem, act, client, graph, clock):
    src = mem.source("C:/repo/docs/README.md")
    f = mem.fact("timeout", "30 seconds", source_id=src)
    stale.mark_changed([{"path": "C:/repo/docs/README.md", "new_hash": "d0"}])
    sweep_to_dormant(act, f)
    clock.t = 2_000_000
    stale.mark_changed([{"path": "C:/repo/docs/README.md", "new_hash": "d1"}], commit="c2")
    assert row(client, graph, f)[2] == "suspect"
