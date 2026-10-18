"""Helpers for the lineage audit regressions: the pre-fix query library and a scale fixture.

``old_client`` runs the queries exactly as they were at edf9a91 (``git archive`` into a scratch dir), so a
rewritten query can be compared row for row with the one it replaces. ``seed_scale`` builds a Source with N
derived facts, each with one reader Step, one Decision and one Handoff.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from knewat.graph.client import GraphClient
from knewat.graph.queries import QueryLibrary

BASELINE = "edf9a91"
HERE = Path(__file__).resolve()
OPEN = 9_999_999_999_999

_old_root: Path | None = None


def old_library() -> QueryLibrary:
    """The query library as committed at BASELINE (extracted once per process)."""
    global _old_root
    if _old_root is None:
        repo = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=HERE.parent,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dest = Path(tempfile.mkdtemp(prefix="knewat_old_queries_"))
        archive = subprocess.run(
            # The product directory had its pre-rename name at BASELINE, so match it by glob.
            ["git", "archive", BASELINE, ":(glob)*/queries/**"],
            cwd=repo,
            capture_output=True,
            check=True,
        ).stdout
        subprocess.run(["tar", "-x", "-C", str(dest)], input=archive, check=True)
        (_old_root,) = dest.glob("*/queries")
    return QueryLibrary(_old_root)


def old_client(client: GraphClient) -> GraphClient:
    """A second client on the same server whose library is the baseline one."""
    kw = client.pool.connection_kwargs
    return GraphClient(host=kw["host"], port=kw["port"], password="", library=old_library())


def seed_scale(client: GraphClient, graph: str, n: int, *, batch: int = 1000) -> None:
    """Source ``SRC`` with ``n`` active facts ``F<i>`` derived from it directly; each fact has a reader Step
    ``ST<i>`` (agent ``ag<i%20>``), a Decision ``D<i>`` BASED_ON it and a Handoff ``H<i>`` CARRIES it.

    Meant for an ``empty_graph`` (no schema): only the id indexes the queries need are created.
    """
    g = client.graph(graph)
    for label in ("Fact", "Source", "Step", "Decision", "Handoff"):
        g.query(f"CREATE INDEX FOR (n:{label}) ON (n.id)")
    g.query("CREATE (:Source {id: 'SRC', uri: 'u:src', kind: 'doc', created_at: 1})")
    for lo in range(0, n, batch):
        rows = [{"i": i} for i in range(lo, min(lo + batch, n))]
        g.query(
            """UNWIND $rows AS r
               MATCH (src:Source {id: 'SRC'})
               CREATE (f:Fact {id: 'F' + toString(r.i), status: 'active', valid_from: 1, valid_to: $open})
                      -[:DERIVED_FROM]->(src)""",
            {"rows": rows, "open": OPEN},
        )
        g.query(
            """UNWIND $rows AS r
               MATCH (f:Fact {id: 'F' + toString(r.i)})
               CREATE (:Step {id: 'ST' + toString(r.i), n: r.i, at: r.i, agent_id: 'ag' + toString(r.i % 20)})
                      -[:READ]->(f)
               CREATE (:Decision {id: 'D' + toString(r.i), at: r.i})-[:BASED_ON]->(f)
               CREATE (:Handoff {id: 'H' + toString(r.i), at: r.i})-[:CARRIES]->(f)""",
            {"rows": rows},
        )


def reset_scale(client: GraphClient, graph: str) -> None:
    """Undo a quarantine / forget (facts back to active and open, decisions unflagged) to run again."""
    g = client.graph(graph)
    g.query(
        "MATCH (f:Fact) WHERE f.status IN ['quarantined', 'forgotten'] "
        "SET f.status = 'active', f.valid_to = $open REMOVE f.prior_status, f.quarantined_at, f.forgotten_at",
        {"open": OPEN},
    )
    g.query("MATCH (d:Decision) REMOVE d.flagged, d.flag_reason")
