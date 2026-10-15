"""Slice 3: ``verify_fact``: the agent re-checks a suspect fact; Plexus records the outcome."""

from __future__ import annotations

import pytest

from plexus.codescan.paths import canonical_path

from .conftest import cypher

P = "C:/repo/app/payments.py"


def _fact(client, graph, fid):
    rows = cypher(
        client,
        graph,
        "MATCH (f:Fact {id:$f}) RETURN f.status, f.valid_from, f.valid_to, f.recorded_at, "
        "coalesce(f.verify_state,'verified'), coalesce(f.verified_at,0), "
        "coalesce(f.verify_after,9999999999999)",
        f=fid,
    )
    return dict(
        zip(
            ["status", "valid_from", "valid_to", "recorded_at", "state", "verified_at", "verify_after"],
            rows[0],
            strict=True,
        )
    )


def _edges(client, graph, fid):
    return cypher(
        client,
        graph,
        "MATCH (:Fact {id:$f})-[r:VERIFIED_BY]->(a:Agent) "
        "RETURN a.id, r.at, r.commit, r.outcome ORDER BY r.at",
        f=fid,
    )


@pytest.fixture
def suspect(stale, mem, clock):
    """A fact anchored to P, made suspect by a change at t=1_500_000; the clock then sits at 2_000_000."""
    f = mem.fact("timeout", "30 seconds")
    stale.anchor_fact(f, P)
    stale.mark_changed([{"path": P, "new_hash": "h0"}])
    stale.mark_changed([{"path": P, "new_hash": "h1"}], commit="c1", at=1_500_000)
    clock.t = 2_000_000
    return f


# -- confirmed -------------------------------------------------------------------------------------------
def test_confirming_a_suspect_fact_makes_it_verified(stale, suspect, client, graph):
    out = stale.verify_fact(suspect, True, agent_id="bob", commit="c2", evidence="read the code")
    assert out == {"fact_id": suspect, "outcome": "confirmed", "flagged_decisions": []}
    f = _fact(client, graph, suspect)
    assert (f["state"], f["verified_at"], f["status"]) == ("verified", 2_000_000, "active")
    assert _edges(client, graph, suspect) == [["bob", 2_000_000, "c2", "confirmed"]]
    # the suspicion stays as history
    assert cypher(
        client, graph, "MATCH (:Change)-[r:SUSPECTED]->(:Fact {id:$f}) RETURN count(r)", f=suspect
    ) == [[1]]
    assert stale.facts_to_verify() == []


def test_confirming_a_fact_that_is_not_suspect_refreshes_verified_at(stale, mem, client, graph, clock):
    f = mem.fact("owner", "alice")
    clock.advance(10)
    stale.verify_fact(f, True, agent_id="bob")
    clock.advance(10)
    stale.verify_fact(f, True, agent_id="carol")
    assert _fact(client, graph, f)["verified_at"] == 1_000_020
    assert [e[0] for e in _edges(client, graph, f)] == ["bob", "carol"]


def test_confirming_clears_a_review_date_that_has_passed(stale, mem, client, graph, clock):
    f = mem.fact("url", "https://acme.example")
    stale.set_review_date(f, 1_000_500)
    clock.t = 1_001_000
    assert [r["fact_id"] for r in stale.facts_to_verify()] == [f]
    stale.verify_fact(f, True, agent_id="bob")
    assert _fact(client, graph, f)["verify_after"] == 9_999_999_999_999
    assert stale.facts_to_verify() == []


def test_confirming_keeps_a_review_date_in_the_future(stale, mem, client, graph, clock):
    f = mem.fact("url", "https://acme.example")
    stale.set_review_date(f, 5_000_000)
    stale.verify_fact(f, True, agent_id="bob")
    assert _fact(client, graph, f)["verify_after"] == 5_000_000


def test_verify_unknown_fact_raises_and_writes_nothing(stale, client, graph):
    with pytest.raises(LookupError):
        stale.verify_fact("nope", True, agent_id="bob")
    with pytest.raises(LookupError):
        stale.verify_fact("nope", False, new_value="x", agent_id="bob")
    assert cypher(client, graph, "MATCH (a:Agent) RETURN count(a)") == [[0]]


# -- changed ---------------------------------------------------------------------------------------------
def test_changed_requires_a_new_value_and_writes_nothing(stale, suspect, client, graph):
    with pytest.raises(ValueError):
        stale.verify_fact(suspect, False, agent_id="bob")
    with pytest.raises(ValueError):
        stale.verify_fact(suspect, False, new_value="   ", agent_id="bob")
    assert _fact(client, graph, suspect)["state"] == "suspect"
    assert cypher(client, graph, "MATCH (f:Fact) RETURN count(f)") == [[1]]


def test_changed_supersedes_and_backdates_to_the_time_of_the_change(
    stale, suspect, mem, client, graph, clock
):
    d = mem.decision(suspect, text="keep the 30 s timeout")
    out = stale.verify_fact(suspect, False, new_value="60 seconds", agent_id="bob", commit="c2")
    assert out["outcome"] == "changed" and out["valid_to"] == 1_500_000
    assert out["flagged_decisions"] == [d] and out["new_fact_id"] != suspect
    old, new = _fact(client, graph, suspect), _fact(client, graph, out["new_fact_id"])
    assert (old["status"], old["valid_to"], old["state"]) == ("superseded", 1_500_000, "verified")
    assert (new["status"], new["valid_from"], new["valid_to"]) == ("active", 1_500_000, 9_999_999_999_999)
    assert new["recorded_at"] == 2_000_000  # when Plexus learned it is unchanged
    assert _edges(client, graph, suspect) == [["bob", 2_000_000, "c2", "changed"]]
    assert cypher(
        client,
        graph,
        "MATCH (d:Decision {id:$d}) RETURN d.flagged, d.flag_reason",
        d=d,
    ) == [[True, f"fact changed: {suspect}"]]
    assert cypher(
        client,
        graph,
        "MATCH (n:Fact {id:$n})-[:SUPERSEDES]->(o:Fact {id:$o}) RETURN count(*)",
        n=out["new_fact_id"],
        o=suspect,
    ) == [[1]]


def test_as_of_answers_with_the_value_valid_at_that_time(stale, suspect, mem, lin):
    out = stale.verify_fact(suspect, False, new_value="60 seconds", agent_id="bob")
    before = lin.as_of("Payments", "timeout", 1_400_000, mem.proj)
    between = lin.as_of("Payments", "timeout", 1_700_000, mem.proj)
    after = lin.as_of("Payments", "timeout", 2_500_000, mem.proj)
    assert before["value"] == "30 seconds" and before["fact_id"] == suspect
    assert between["value"] == "60 seconds" and between["fact_id"] == out["new_fact_id"]
    assert after["value"] == "60 seconds"
    assert before["also_valid"] == [] and between["also_valid"] == []  # windows are contiguous


def test_changed_without_a_suspecting_change_uses_the_current_time(stale, mem, client, graph, clock):
    f = mem.fact("owner", "alice")
    clock.t = 1_700_000
    out = stale.verify_fact(f, False, new_value="bob", agent_id="bob")
    assert out["valid_to"] == 1_700_000
    assert _fact(client, graph, out["new_fact_id"])["valid_from"] == 1_700_000


def test_backdating_never_moves_valid_to_before_the_old_facts_valid_from(stale, mem, client, graph, clock):
    f = mem.fact("timeout", "30 seconds")  # valid_from 1_000_000
    stale.anchor_fact(f, P)
    stale.mark_changed([{"path": P, "new_hash": "h0"}])
    stale.mark_changed([{"path": P, "new_hash": "h1"}], at=900_000)  # a change older than the fact itself
    clock.t = 2_000_000
    out = stale.verify_fact(f, False, new_value="60 seconds", agent_id="bob")
    assert out["valid_to"] == 2_000_000
    assert _fact(client, graph, f)["valid_to"] == 2_000_000


def test_the_newest_suspecting_change_before_now_is_used(stale, mem, clock):
    f = mem.fact("timeout", "30 seconds")
    stale.anchor_fact(f, P)
    stale.mark_changed([{"path": P, "new_hash": "h0"}])
    stale.mark_changed([{"path": P, "new_hash": "h1"}], at=1_200_000)
    stale.mark_changed([{"path": P, "new_hash": "h2"}], at=1_800_000)
    stale.mark_changed([{"path": P, "new_hash": "h3"}], at=3_000_000)  # in the future: ignored
    clock.t = 2_000_000
    assert stale.verify_fact(f, False, new_value="60 seconds", agent_id="bob")["valid_to"] == 1_800_000


def test_evidence_that_is_a_path_becomes_a_source_the_new_fact_derives_from(stale, suspect, client, graph):
    out = stale.verify_fact(
        suspect, False, new_value="60 seconds", agent_id="bob", evidence="c:\\\\repo\\\\app\\\\payments.py"
    )
    rows = cypher(
        client,
        graph,
        "MATCH (:Fact {id:$n})-[:DERIVED_FROM]->(s:Source) RETURN s.uri, s.kind",
        n=out["new_fact_id"],
    )
    assert rows == [[canonical_path(P), "code"]]


def test_free_text_evidence_is_kept_on_the_edge_without_a_source(stale, suspect, client, graph):
    stale.verify_fact(suspect, False, new_value="60 seconds", agent_id="bob", evidence="ran the tests")
    assert cypher(client, graph, "MATCH (s:Source) RETURN count(s)") == [[0]]
    assert cypher(client, graph, "MATCH ()-[r:VERIFIED_BY]->() RETURN r.evidence") == [["ran the tests"]]


def test_changed_to_the_same_value_counts_as_confirmed(stale, suspect, client, graph):
    out = stale.verify_fact(suspect, False, new_value="30  Seconds", agent_id="bob")
    assert out["outcome"] == "confirmed" and "new_fact_id" not in out
    assert _fact(client, graph, suspect)["state"] == "verified"
    assert cypher(client, graph, "MATCH (f:Fact) RETURN count(f)") == [[1]]


def test_only_a_current_fact_can_be_changed(stale, suspect):
    out = stale.verify_fact(suspect, False, new_value="60 seconds", agent_id="bob")
    with pytest.raises(ValueError):
        stale.verify_fact(suspect, False, new_value="90 seconds", agent_id="bob")
    assert out["new_fact_id"]
    # confirming a superseded fact is harmless (it refreshes verified_at only)
    assert stale.verify_fact(suspect, True, agent_id="bob")["outcome"] == "confirmed"


def test_the_new_fact_is_not_suspect_and_old_decisions_are_the_only_ones_flagged(
    stale, suspect, mem, client, graph
):
    d_old = mem.decision(suspect)
    out = stale.verify_fact(suspect, False, new_value="60 seconds", agent_id="bob")
    d_new = mem.decision(out["new_fact_id"], text="uses the new value")
    assert stale.facts_to_verify() == []
    assert cypher(client, graph, "MATCH (d:Decision {id:$d}) RETURN coalesce(d.flagged,false)", d=d_new) == [
        [False]
    ]
    assert out["flagged_decisions"] == [d_old]


# -- the known non-atomic path ---------------------------------------------------------------------------
class _FailBackdate:
    """A client whose ``staleness/backdate`` write fails (the process died between the two statements)."""

    def __init__(self, inner):
        self._inner = inner

    def rw(self, graph, name, params=None, *a, **kw):
        if name == "staleness/backdate":
            raise RuntimeError("simulated failure between the two statements")
        return self._inner.rw(graph, name, params, *a, **kw)

    def __getattr__(self, item):
        return getattr(self._inner, item)


def test_a_failure_between_the_two_statements_keeps_the_new_value_but_not_the_backdate(
    stale, suspect, mem, eng, client, graph, clock
):
    """Documented in docs/staleness.md: supersede and backdate are two statements (no transactions)."""
    from plexus.staleness import Staleness

    d = mem.decision(suspect)
    broken = Staleness(_FailBackdate(client), graph, engram=eng, clock=clock)
    with pytest.raises(RuntimeError):
        broken.verify_fact(suspect, False, new_value="60 seconds", agent_id="bob")
    new_id = cypher(client, graph, "MATCH (f:Fact {value:'60 seconds'}) RETURN f.id")[0][0]
    new, old = _fact(client, graph, new_id), _fact(client, graph, suspect)
    assert new["status"] == "active"  # the new value is recorded and is the current one
    # what is missing: the backdate, the verification and the decision flag
    assert old["status"] == "superseded" and old["valid_to"] == new["valid_from"] == 2_000_000
    assert old["state"] == "suspect" and _edges(client, graph, suspect) == []
    assert cypher(client, graph, "MATCH (d:Decision {id:$d}) RETURN coalesce(d.flagged,false)", d=d) == [
        [False]
    ]
    # the superseded fact is no longer current, so it has left facts_to_verify and verify_fact refuses it
    assert stale.facts_to_verify() == []
    with pytest.raises(ValueError, match="superseded"):
        stale.verify_fact(suspect, False, new_value="60 seconds", agent_id="bob")


# -- found by the real Claude Code run (P7-int): a small correction is not a duplicate ----------------------
LONG_OLD = (
    "eSewa and Khalti (GATEWAY_METHODS = esewa, khalti). Gateway methods return a PENDING payment plus an "
    "initiation (eSewa signed form / Khalti redirect URL); status becomes COMPLETED only after server-side "
    "verification via POST /payments/{id}/confirm. Legacy imepay is aliased to Khalti; non-gateway methods "
    "complete immediately."
)
LONG_NEW = LONG_OLD.replace("Legacy imepay is aliased to Khalti", "Legacy imepay is no longer aliased to Khalti")


def test_a_small_correction_of_a_long_fact_is_recorded_not_swallowed_as_a_paraphrase(
    stale, mem, client, graph, clock
):
    """The real run corrected one clause of a long fact; ``assert_fact`` called it a paraphrase duplicate of the old
    fact, so verify_fact reported 'changed' while the old text stayed current. A corrected value must always win."""
    f = mem.fact("payment gateways", LONG_OLD)
    stale.anchor_fact(f, P)
    stale.mark_changed([{"path": P, "new_hash": "h0"}])
    stale.mark_changed([{"path": P, "new_hash": "h1"}], commit="c1", at=1_500_000)
    clock.t = 2_000_000
    out = stale.verify_fact(f, False, new_value=LONG_NEW, agent_id="bob")
    assert out["outcome"] == "changed" and out["new_fact_id"] != f
    rows = cypher(client, graph, "MATCH (x:Fact) RETURN x.id, x.status, x.value ORDER BY x.recorded_at")
    assert [(r[1], r[2]) for r in rows] == [("superseded", LONG_OLD), ("active", LONG_NEW)]
