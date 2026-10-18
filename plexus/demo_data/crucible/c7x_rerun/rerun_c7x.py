"""Rebuild demo_data/crucible/c7x_results.json for the five C7X arms (P, P-mcp, B0, B1, B2).

`crucible l1 --arms` only accepts the L1 arms (B0, B1, B2, P); P-mcp is not selectable there, so this calls
`plexus.crucible.l1.run_test` (the same function the CLI uses) for each arm and writes the c7x_results.json shape
(per arm: violations, metrics, details, seconds). One sequential run per arm, fastembed, seed 1000.

    PLEXUS_EMBEDDER=fastembed python rerun_c7x.py <db port> <out dir>
"""

import json
import sys
import tempfile
import time
from pathlib import Path

from plexus.crucible.config import L1Config
from plexus.crucible.harness import Env
from plexus.crucible.l1 import run_test
from plexus.crucible.util import iso_utc

port, out = int(sys.argv[1]), Path(sys.argv[2])
env = Env.from_environ(root=tempfile.mkdtemp(prefix="c7x-"), embedder="fastembed")
env.port = port
cfg = L1Config(reps=1, tests=("C7X",))
arms = {}
for arm in ("P", "P-mcp", "B0", "B1", "B2"):
    t0 = time.time()
    r = run_test(env, arm, "C7X", cfg, print)
    d = r["runs_detail"][0]
    arms[arm] = {
        "violations": d["violations"],
        "metrics": d["metrics"],
        "details": d["details"],
        "seconds": round(time.time() - t0, 1),
    }
doc = {
    "note": "C7X run with the real fastembed embedder (BAAI/bge-small-en-v1.5), sequential, one run per arm; see docs/BASELINE.md "
    "'C7 extended results' and 'Re-verification on main (2026-10-18)'. Rebuilt by rerun_c7x.py (plexus.crucible.l1.run_test per arm) at "
    + iso_utc()
    + ".",
    "arms": arms,
}
out.mkdir(parents=True, exist_ok=True)
(out / "c7x_results.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
print("wrote", out / "c7x_results.json")
