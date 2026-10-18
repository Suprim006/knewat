"""P12 fix 2 kill test (L6-F, Task variant): a writer looping create_tasks / claim_next_task / complete_task /
fail_task / reopen_task through the P-mcp backend is SIGKILLed 50 times (random 0-400 ms).

Orphan = a task state change (create, claim, complete, fail, reopen; each is one ``version`` step) without its own
``(Step)-[:WROTE]->(Task)`` edge: a Task must have exactly ``version + 1`` WROTE edges (see
``knewat.crucible.l6.crash_tasks``).

Before the fix (the five tools linked by a second ``link_step`` statement; ``--legacy`` reproduces that), run with
seed 20261018 and 50 kills: 41 of 1,287 expected
WROTE edges were missing (40 of 645 tasks; 808 acknowledged calls).
After the fix (WROTE created inside each tool's own write statement; same seed, 858 acknowledged calls, 1,333 of
1,333 edges present): 0 orphan writes, 0 orphan tasks, 0 duplicate
edges, 0 lost acknowledged writes.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid

from tests.conftest import TEST_DB_HOST, TEST_DB_PORT

from knewat.crucible.l6 import crash_tasks
from knewat.graph.tenancy import graph_name


def test_no_orphan_task_writes_after_50_sigkills(client):
    root = tempfile.mkdtemp(prefix="l6ft-")
    tenant = f"l6ft_p_{uuid.uuid4().hex[:6]}"
    try:
        res = crash_tasks.kill_loop(50, root, tenant, TEST_DB_HOST, TEST_DB_PORT, seed=20261018)
    finally:
        client.delete_graph(graph_name(tenant))
        shutil.rmtree(root, ignore_errors=True)
    assert res["totals"]["tasks"] > 0 and res["acknowledged_calls"] > 0, res
    assert res["orphan_writes"] == 0 and res["orphan_tasks"] == 0, res
    assert res["duplicate_wrote_edges"] == 0, res
    assert res["lost_acknowledged_total"] == 0, res
