"""FIX-P7 P7-04 / P7-10: a doubted fact is not strengthened by being recalled.

"Doubted" is the contract rule (``verify_state = 'suspect'`` OR ``verify_after <= t``) evaluated at the time
of the READ, not at the time of the question: a recall taken while the fact was doubted never counts, even
after the fact was verified again, and a recall taken before the doubt keeps counting.
"""

from __future__ import annotations

import pytest

from plexus.activation import Activation, Settings
from plexus.activation.model import DAY_MS

from .conftest import reads, write

NOW = 5_000 * DAY_MS


@pytest.fixture
def act(client, graph) -> Activation:
    return Activation(client, graph, Settings())


@pytest.fixture
def fact(eng, scope):
    r = eng.assert_fact("API", "database", "PostgreSQL 16", scope, "alice", now=NOW - 20 * DAY_MS)
    return r["fact_id"]


def recall(lin, scope, fact, at, n=1):
    st = lin.record_step("bob", n, at=at)
    lin.record_recall("bob", st, "q", scope, 3, [{"fact_id": fact}], now=at)
    return st


def recall_times(act, fact, now=NOW):
    return sorted(e.t for e in act.compute([fact], now)[fact].events if e.kind == "recall")


def test_a_recall_after_the_review_date_does_not_count(act, lin, scope, fact, client, graph):
    """P7-04: suspect by the review-date branch of the rule, not by verify_state."""
    write(client, graph, "MATCH (f:Fact {id:$f}) SET f.verify_after = $t", f=fact, t=NOW - 3 * DAY_MS)
    st = recall(lin, scope, fact, NOW - DAY_MS)
    assert reads(client, graph, st, fact) == [["recall", NOW - DAY_MS]]
    fa = act.compute([fact], NOW)[fact]
    assert fa.verify_state == "verified"  # only the date makes it suspect
    assert recall_times(act, fact) == []


def test_a_recall_before_the_review_date_still_counts_after_it_passed(act, lin, scope, fact, client, graph):
    """The rule is evaluated at the READ's time, not at the time of the question."""
    write(client, graph, "MATCH (f:Fact {id:$f}) SET f.verify_after = $t", f=fact, t=NOW - 3 * DAY_MS)
    recall(lin, scope, fact, NOW - 5 * DAY_MS)  # the date had not passed yet
    recall(lin, scope, fact, NOW - 2 * DAY_MS, n=2)  # it had
    assert recall_times(act, fact) == [NOW - 5 * DAY_MS]


def test_recalls_made_while_suspect_stay_discounted_after_the_fact_is_verified(
    act, lin, scope, fact, client, graph
):
    """P7-10: the doubted period must not retroactively strengthen the fact."""
    recall(lin, scope, fact, NOW - 9 * DAY_MS)  # before the doubt: counts
    write(
        client,
        graph,
        "MATCH (f:Fact {id:$f}) SET f.verify_state = 'suspect', f.suspect_since = $t",
        f=fact,
        t=NOW - 8 * DAY_MS,
    )
    for i in range(3):  # while doubted: do not count
        recall(lin, scope, fact, NOW - (6 - i) * DAY_MS, n=10 + i)
    # an agent re-checks the fact
    write(
        client,
        graph,
        "MATCH (f:Fact {id:$f}) SET f.verify_state = 'verified', f.verified_at = $t "
        "MERGE (a:Agent {id:'bob'}) CREATE (f)-[:VERIFIED_BY {at:$t, commit:'', outcome:'confirmed'}]->(a)",
        f=fact,
        t=NOW - 2 * DAY_MS,
    )
    recall(lin, scope, fact, NOW - DAY_MS, n=20)  # verified again: counts
    assert recall_times(act, fact) == [NOW - 9 * DAY_MS, NOW - DAY_MS]


def test_a_flagless_legacy_read_falls_back_to_the_current_state(act, lin, scope, fact, client, graph):
    """READ edges written before the flag existed are judged by the fact's current state, as before."""
    st = recall(lin, scope, fact, NOW - DAY_MS)
    write(client, graph, "MATCH ()-[r:READ]->(:Fact {id:$f}) REMOVE r.suspect", f=fact)
    write(client, graph, "MATCH (f:Fact {id:$f}) SET f.verify_after = $t", f=fact, t=NOW - 2 * DAY_MS)
    assert recall_times(act, fact) == []
    assert reads(client, graph, st, fact) == [["recall", NOW - DAY_MS]]


def test_a_use_is_never_discounted(act, lin, scope, fact, client, graph):
    write(client, graph, "MATCH (f:Fact {id:$f}) SET f.verify_after = $t", f=fact, t=NOW - 3 * DAY_MS)
    st = lin.record_step("bob", 1, at=NOW - DAY_MS)
    lin.link_step(st, read_ids=[fact])
    assert [e.kind for e in act.compute([fact], NOW)[fact].events if e.kind == "use"] == ["use"]
