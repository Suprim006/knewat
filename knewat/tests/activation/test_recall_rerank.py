"""Slice 4b: ``Engram.recall`` with forgetting on, against a real FalkorDB.

The embedder puts a fact at an exact cosine distance from the query: a value containing ``~0.30`` is 0.30 away
from the text ``QUERY`` (and nearly orthogonal to everything else), so relevance is exact and only the
activation can change the order.
"""

from __future__ import annotations

import hashlib
import math
import re
import time

import pytest

from plexus.embed import HashEmbedder
from plexus.embed.base import DIM
from plexus.engram import Engram

from .conftest import DAY, HOUR, write

_MARK = re.compile(r"~(\d+\.\d+)")


class AngleEmbedder:
    """``QUERY`` -> e0; text with ``~d`` -> unit vector at cosine distance d from e0; anything else hashed."""

    def __init__(self) -> None:
        self.dim = DIM
        self._h = HashEmbedder()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        if text.strip() == "QUERY":
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


def now_ms() -> int:
    return time.time_ns() // 1_000_000


@pytest.fixture
def aeng(client, graph) -> Engram:
    return Engram(client, graph, AngleEmbedder())


class Maker:
    def __init__(self, eng, scope, lin, client, graph):
        self.eng, self.scope, self.lin, self.client, self.graph = eng, scope, lin, client, graph
        self.steps = 0

    def fact(self, name: str, dist: float, age_days: float = 60, *, surprise: float = 0.0, agent="alice"):
        fid = self.eng.assert_fact(
            f"Thing {name}",
            "note",
            f"{name} ~{dist:.2f}",
            self.scope,
            agent,
            now=now_ms() - round(age_days * DAY),
        )["fact_id"]
        write(self.client, self.graph, "MATCH (f:Fact {id:$f}) SET f.surprise = $s", f=fid, s=surprise)
        return fid

    def use(self, fid: str, ago_ms: int, how="use") -> None:
        self.steps += 1
        st = self.lin.record_step("reader", self.steps, at=now_ms() - ago_ms)
        if how == "use":
            self.lin.link_step(st, read_ids=[fid])
        else:
            self.lin.record_recall(
                "reader", st, "q", self.scope, 3, [{"fact_id": fid}], now=now_ms() - ago_ms
            )


@pytest.fixture
def mk(aeng, scope, lin, client, graph) -> Maker:
    return Maker(aeng, scope, lin, client, graph)


def ids(rows):
    return [r["fact_id"] for r in rows]


def test_equal_relevance_the_recently_used_fact_ranks_first(aeng, scope, mk):
    old = mk.fact("old", 0.30)
    used = mk.fact("used", 0.30)
    mk.use(used, HOUR)
    assert ids(aeng.recall("QUERY", scope, k=2, forgetting=False)) in ([old, used], [used, old])
    assert ids(aeng.recall("QUERY", scope, k=2)) == [used, old]


def test_a_recalled_but_never_used_fact_gains_little(aeng, scope, mk):
    plain = mk.fact("plain", 0.30)
    seen = mk.fact("seen", 0.30)
    used = mk.fact("used", 0.30)
    mk.use(seen, HOUR, how="recall")
    mk.use(used, HOUR, how="use")
    got = ids(aeng.recall("QUERY", scope, k=3))
    assert got == [used, seen, plain]


def test_the_floor_a_relevant_unused_fact_still_beats_an_irrelevant_used_one(aeng, scope, mk):
    relevant = mk.fact("relevant", 0.10, age_days=400)
    irrelevant = mk.fact("irrelevant", 0.60, age_days=400)
    for i in range(3):
        mk.use(irrelevant, (i + 1) * HOUR)
    assert ids(aeng.recall("QUERY", scope, k=2)) == [relevant, irrelevant]


def test_the_candidate_pool_is_twice_k_so_a_used_fact_just_outside_the_top_k_can_rise(
    aeng, scope, mk, monkeypatch
):
    monkeypatch.setenv(
        "PLEXUS_ACT_FLOOR", "0.5"
    )  # a wider multiplier range than the 0.9 default, to see the rise
    near = mk.fact("near", 0.30, age_days=200)
    farther = mk.fact("farther", 0.36, age_days=200)
    mk.use(farther, HOUR)
    mk.use(farther, 2 * HOUR)
    assert ids(aeng.recall("QUERY", scope, k=1, forgetting=False)) == [near]
    assert ids(aeng.recall("QUERY", scope, k=1)) == [farther]


def test_a_decision_supported_fact_90_days_old_is_not_demoted_below_neutral(aeng, scope, mk, relay, lin):
    protected = mk.fact("protected", 0.30, age_days=90)
    plain = mk.fact("plain", 0.30, age_days=90)
    relay.register_agent("alice", "alice", "x", "t")
    relay.create_tasks([{"id": "t1", "title": "ship"}])
    relay.record_decision("alice", "t1", "rely on it", [protected], now=now_ms() - 90 * DAY)
    rows = aeng.recall("QUERY", scope, k=2)
    assert ids(rows) == [protected, plain]
    by = {r["fact_id"]: r for r in rows}
    assert by[protected]["protected"] is True and by[plain]["protected"] is False


def test_a_surprising_fact_outranks_an_equally_relevant_equally_old_plain_one(aeng, scope, mk):
    plain = mk.fact("plain", 0.30, age_days=60, surprise=0.0)
    contra = mk.fact("contra", 0.30, age_days=60, surprise=0.9)
    assert ids(aeng.recall("QUERY", scope, k=2)) == [contra, plain]


def test_rows_carry_the_p7_fields(aeng, scope, mk):
    f = mk.fact("one", 0.30, surprise=0.6)
    row = aeng.recall("QUERY", scope, k=1)[0]
    assert row["fact_id"] == f
    assert isinstance(row["activation"], float) and row["protected"] is False
    assert row["surprise"] == pytest.approx(0.6)
    assert (row["verify_state"], row["suspect_since"], row["suspect_reason"]) == ("verified", 0, None)
    assert row["score"] == pytest.approx(0.30, abs=1e-4), "score is still the cosine distance"


def test_the_char_budget_is_applied_after_the_cut(aeng, scope, mk):
    for i in range(4):
        mk.fact(f"f{i}", 0.30 + i * 0.01)
    rows = aeng.recall("QUERY", scope, k=4, budget_chars=60)
    assert 1 <= len(rows) < 4


# ---------------------------------------------------------------- suspect rows
def test_a_suspect_fact_is_still_returned_with_its_reason(aeng, scope, mk, client, graph):
    f = mk.fact("code", 0.20)
    write(
        client,
        graph,
        "MATCH (f:Fact {id:$f}) SET f.verify_state = 'suspect', f.suspect_since = $t "
        "CREATE (:Change {id:'c1', commit:'abc123', at:$t, paths:'[\"C:/repo/app.py\", \"C:/repo/b.py\"]'})"
        "-[:SUSPECTED {at:$t}]->(f)",
        f=f,
        t=now_ms() - HOUR,
    )
    row = aeng.recall("QUERY", scope, k=1)[0]
    assert row["fact_id"] == f
    assert row["verify_state"] == "suspect" and row["suspect_since"] > 0
    assert row["suspect_reason"] == "changed in abc123 (C:/repo/app.py)"


def test_the_newest_change_gives_the_reason_and_an_empty_commit_is_the_working_tree(
    aeng, scope, mk, client, graph
):
    f = mk.fact("code", 0.20)
    t = now_ms()
    write(
        client,
        graph,
        "MATCH (f:Fact {id:$f}) SET f.verify_state = 'suspect', f.suspect_since = $t "
        "CREATE (:Change {id:'c1', commit:'old', at:$t - 5000, paths:'[\"C:/old.py\"]'})-[:SUSPECTED]->(f) "
        "CREATE (:Change {id:'c2', commit:'', at:$t, paths:'[\"C:/new.py\"]'})-[:SUSPECTED]->(f)",
        f=f,
        t=t - HOUR,
    )
    assert aeng.recall("QUERY", scope, k=1)[0]["suspect_reason"] == "changed in working tree (C:/new.py)"


def test_a_passed_review_date_makes_the_fact_suspect_without_a_change(aeng, scope, mk, client, graph):
    f = mk.fact("url", 0.20)
    write(client, graph, "MATCH (f:Fact {id:$f}) SET f.verify_after = $t", f=f, t=now_ms() - DAY)
    row = aeng.recall("QUERY", scope, k=1)[0]
    assert (row["verify_state"], row["suspect_reason"]) == ("suspect", "review date passed")
    assert row["suspect_since"] > 0
    write(client, graph, "MATCH (f:Fact {id:$f}) SET f.verify_after = $t", f=f, t=now_ms() + DAY)
    assert aeng.recall("QUERY", scope, k=1)[0]["verify_state"] == "verified"


def test_a_suspect_flag_with_no_change_node_still_gets_a_reason(aeng, scope, mk, client, graph):
    f = mk.fact("odd", 0.20)
    write(client, graph, "MATCH (f:Fact {id:$f}) SET f.verify_state = 'suspect', f.suspect_since = 5", f=f)
    assert aeng.recall("QUERY", scope, k=1)[0]["suspect_reason"] == "marked suspect"


# ---------------------------------------------------------------- dormant
def test_dormant_facts_are_hidden_unless_asked_for_and_as_of_includes_them(aeng, scope, mk, client, graph):
    live = mk.fact("live", 0.20)
    dormant = mk.fact("dormant", 0.10)
    write(client, graph, "MATCH (f:Fact {id:$f}) SET f.status = 'dormant'", f=dormant)
    assert ids(aeng.recall("QUERY", scope, k=5)) == [live]
    assert set(ids(aeng.recall("QUERY", scope, k=5, include_dormant=True))) == {live, dormant}
    assert set(ids(aeng.recall("QUERY", scope, k=5, as_of=now_ms()))) == {live, dormant}
    assert dormant in ids(aeng.recall("QUERY", scope, k=5, forgetting=False, include_dormant=True))
