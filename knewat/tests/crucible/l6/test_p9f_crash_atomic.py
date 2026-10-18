"""P9-f: a fact, decision or handoff and its Step / WROTE provenance are written atomically (Crucible L6-F).

L6-F killed a writer process 200 times (``TerminateProcess`` on Windows, SIGKILL elsewhere) at random moments
and found 94 of 1,240 records (7.6%) with no Step/WROTE link, and 9 facts without the DERIVED_FROM link they
were written with: the service path wrote the memory, then the Step, then the links, in separate statements.
This runs the same kill loop (``crucible.l6.crash``) at a small size against the Plexus arm.
"""

from __future__ import annotations

import os
import uuid

import pytest

from plexus.crucible.l6 import crash
from plexus.graph.client import GraphClient
from plexus.graph.tenancy import graph_name

DB_HOST = "127.0.0.1"
DB_PORT = int(os.environ.get("PLEXUS_TEST_DB_PORT", "6310"))
KILLS = int(os.environ.get("PLEXUS_TEST_CRASH_KILLS", "25"))


@pytest.mark.integration
def test_repeated_kills_leave_no_record_without_its_provenance(tmp_path):
    tenant = "l6fx_" + uuid.uuid4().hex[:10]
    try:
        res = crash.kill_loop(
            "P", KILLS, str(tmp_path), tenant, DB_HOST, DB_PORT, seed=20261016, log=lambda s: None
        )
    finally:
        GraphClient(host=DB_HOST, port=DB_PORT).delete_graph(graph_name(tenant))
    total = sum(res["totals"].values())
    assert total >= 40, res  # enough records for the check to mean something (~5 per kill)
    assert res["lost_acknowledged_total"] == 0, res
    assert res["orphans_total"] == 0, res
    assert res["missing_derived_from"] == 0, res
