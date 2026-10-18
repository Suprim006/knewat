"""P9-int kill test (L6-F): a writer process looping assert_fact / record_decision / handoff is SIGKILLed 50 times.

Before the fix 94 of 1,240 acknowledged-or-in-flight records had no ``(Step)-[:WROTE]->`` edge (the memory write and
the Step/WROTE link were separate statements). Now the write statement of those three tools creates the edge itself.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid

from tests.conftest import TEST_DB_HOST, TEST_DB_PORT

from plexus.crucible.l6 import crash
from plexus.graph.tenancy import graph_name


def test_no_orphans_after_50_sigkills(client):
    root = tempfile.mkdtemp(prefix="l6fold-")
    tenant = f"l6f_p_{uuid.uuid4().hex[:6]}"
    try:
        res = crash.kill_loop("P", 50, root, tenant, TEST_DB_HOST, TEST_DB_PORT, seed=20261017)
    finally:
        client.delete_graph(graph_name(tenant))
        shutil.rmtree(root, ignore_errors=True)
    totals = res["totals"]
    assert totals["facts"] > 0 and totals["decisions"] > 0 and totals["handoffs"] > 0, totals
    assert res["orphans"] == {"facts": 0, "decisions": 0, "handoffs": 0}, res
    assert res["lost_acknowledged_total"] == 0, res
