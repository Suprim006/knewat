"""P12-F3 kill test: ``verify_fact(changed)`` interrupted by SIGKILL never leaves a *silent* inconsistency.

A writer process loops assert_fact / record_decision / verify_fact(changed); the parent kills it 40 times after a random
0-400 ms. ``PLEXUS_TEST_VERIFY_GAP_MS=60`` (a test hook between the supersede and the backdate) widens the window and is
set for the old and the new run alike. Silent = an old fact superseded by a verification with neither a completed
verification (``VERIFIED_BY {outcome:'changed'}``) nor ``verify_degraded``; its Decisions are then unflagged too.

Measured (seed 20261016, 40 kills, same hook):
  old code (no marker before the supersede): 92 superseded, 72 completed, 20 SILENT, 20 unflagged decisions on them.
  new code (staleness/mark_unfinished first): 88 superseded, 66 completed, 22 marked unfinished, 0 silent,
  0 unflagged decisions; 4 more facts were killed after the marker but before the supersede (active, marked).
"""

from __future__ import annotations

import uuid

from tests.conftest import TEST_DB_HOST, TEST_DB_PORT

from plexus.crucible.l6 import verify_crash
from plexus.graph.tenancy import graph_name


def test_no_silent_inconsistency_after_40_sigkills(client):
    graph = graph_name(f"vcrash_{uuid.uuid4().hex[:6]}")
    try:
        res = verify_crash.kill_loop(40, TEST_DB_HOST, TEST_DB_PORT, graph, seed=20261016)
    finally:
        client.delete_graph(graph)
    assert res["superseded_by_verify"] > 0, res
    assert res["silent"] == 0 and res["silent_unflagged_decisions"] == 0, res
