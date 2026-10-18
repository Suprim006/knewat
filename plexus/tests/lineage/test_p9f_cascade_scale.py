"""P9-f: the write cascades (quarantine, release_quarantine, forget_source) on a 1,000-fact blast, exactly.

They had the same chained ``UNWIND fs`` joins as ``impact`` (grouped by the whole fact list): quarantine of a
1,000-fact diamond blast was cancelled by the server (> 5 s); now it takes about 2 s. Above that the cost is
the bulk SET itself: on FalkorDB 6.0.2 a SET on N nodes of a label with a UNIQUE constraint grows ~N^2.6
(500 nodes 0.1 s, 1,000 0.6 s, 2,000 4.0 s on a bare graph), so a 5,000-fact quarantine in ONE
statement still does not fit the 10 s TIMEOUT_MAX. That limit is reported in docs/BASELINE.md (L6 post-fix).
"""

from __future__ import annotations

import time

from plexus.lineage import Lineage

from .blast_p9f import build_blast
from .conftest import cypher


def _timed(fn, *a, **kw):
    t0 = time.perf_counter()
    out = fn(*a, **kw)
    return out, time.perf_counter() - t0


def test_quarantine_release_and_forget_on_a_1000_fact_blast(client, graph):
    b = build_blast(client, graph, n=1000, levels=12)
    lin = Lineage(client, graph)
    q, wall = _timed(lin.quarantine, b["source"], depth=12, now=2_000_000_000_000)
    assert wall < 5.0, f"quarantine took {wall:.2f} s"
    assert q["fact_ids"] == sorted(b["facts"]) and q["truncated"] is False
    assert q["readers_total"] == b["steps"] and q["agents"] == b["agents"]
    assert q["decisions_total"] == len(b["decisions"]) and q["handoffs_total"] == len(b["handoffs"])
    assert len(q["readers"]) == 500 and q["detail_truncated"] is True
    # the listed readers are the earliest 500 reads (by step time), as before
    ats = sorted(r[0] for r in cypher(client, graph, "MATCH (s:Step)-[:READ]->(:Fact) RETURN s.at"))
    assert [r["at"] for r in q["readers"]] == ats[:500]
    statuses = cypher(client, graph, "MATCH (f:Fact) RETURN f.status, count(f)")
    assert statuses == [["quarantined", 1000]]

    rel, wall = _timed(lin.release_quarantine, b["source"], depth=12)
    assert wall < 5.0 and len(rel["fact_ids"]) == 1000

    f, wall = _timed(lin.forget_source, b["source"], depth=12, now=2_000_000_000_000)
    assert wall < 5.0, f"forget_source took {wall:.2f} s"
    assert f["fact_ids"] == sorted(b["facts"])
    assert f["decisions_total"] == len(b["decisions"]) and f["handoffs_total"] == len(b["handoffs"])
    flagged = cypher(client, graph, "MATCH (d:Decision) WHERE d.flagged RETURN count(d)")
    assert flagged == [[len(b["decisions"])]]
