import shutil
import tempfile
import time

from knewat.crucible.l7 import common, i, i_conc

port = 6393
doc = common.envelope(
    "i",
    "127.0.0.1",
    port,
    time.time(),
    "script: i_conc.rerun_a_cell FalkorDB cas+pessimistic W=200 ops=50 budget=1500"
    " (rerun of the two cells that hit the 240 s budget under concurrent load) on port 6393",
)
doc.update({"scale": "full", "parts": {}, "db_port": port, "i4_busy_timeout_ms": 10000})
root = tempfile.mkdtemp(prefix="l7i-")
try:
    rows = []
    for mode in ("cas", "pessimistic"):
        i.log(f"rerun {mode} W=200")
        rows.append(i_conc.rerun_a_cell("FalkorDB", mode, 200, 50, 1500.0, "127.0.0.1", port, root))
        i.log(
            str({k: rows[-1][k] for k in ("final", "lost_acked", "retries", "wall_s", "completed_in_budget")})
        )
    doc["parts"]["I4"] = {"a": rows, "b": [], "rerun": True}
finally:
    shutil.rmtree(root, ignore_errors=True)
print(common.write(doc, common.DEMO, i.report_md(doc)))
