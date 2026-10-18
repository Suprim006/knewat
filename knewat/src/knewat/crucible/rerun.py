"""Re-run selected cells of a finished run and splice them into its results (``crucible rerun``).

Used when a harness bug invalidated a few cells: only those cells are executed again, the original results are kept
under ``run.reruns[*].superseded`` with the reason, and the summary / report are rebuilt. Nothing is retried silently:
the report lists every replaced cell and what it showed before.

Cell syntax (``--cell``, repeatable):  ``L1:<arm>:<test>``  e.g. ``L1:P:C1``;  ``L4:claim:<arm>:<workers>``  e.g.
``L4:claim:P:200``;  ``L4:embedder`` (the embedding-throughput probe).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from knewat.crucible import environment
from knewat.crucible import results as R
from knewat.crucible.config import L1Config, L4Config
from knewat.crucible.harness import Env
from knewat.crucible.util import iso_utc


def _tuples(d: dict[str, Any]) -> dict[str, Any]:
    return {k: tuple(v) if isinstance(v, list) else v for k, v in d.items()}


def rerun(
    base: Path, cells: list[str], reason: str, env: Env, log: Callable[[str], None] = print
) -> tuple[Path, dict[str, Any]]:
    from knewat.crucible.l1 import run_test
    from knewat.crucible.l4 import claim_point, embedder_probe

    path = base / "results.json" if base.is_dir() else base
    res = json.loads(path.read_text(encoding="utf-8"))
    out_dir = path.parent
    cfg = res["config"]
    l1_cfg = (
        L1Config(**_tuples({k: v for k, v in cfg["l1"].items() if k != "seeds"})) if "l1" in cfg else None
    )
    l4_cfg = L4Config(**_tuples(cfg["l4"])) if "l4" in cfg else None
    superseded: list[dict[str, Any]] = []
    for cell in cells:
        parts = cell.split(":")
        if parts[0] == "L1" and len(parts) == 3 and l1_cfg is not None:
            _, arm, test = parts
            old = res["layers"]["L1"]["arms"][arm]["tests"][test]
            superseded.append({"cell": cell, "result": {k: v for k, v in old.items() if k != "runs_detail"}})
            log(f"rerun {cell}")
            res["layers"]["L1"]["arms"][arm]["tests"][test] = run_test(env, arm, test, l1_cfg, log)
        elif parts[:2] == ["L4", "claim"] and len(parts) == 4 and l4_cfg is not None:
            arm, w = parts[2], int(parts[3])
            sweep = res["layers"]["L4"]["claim_sweep"]
            idx = next(i for i, p in enumerate(sweep) if p["arm"] == arm and p["workers"] == w)
            superseded.append({"cell": cell, "result": sweep[idx]})
            log(f"rerun {cell}")
            sweep[idx] = claim_point(env, arm, w, l4_cfg)
        elif parts == ["L4", "embedder"] and l4_cfg is not None:
            superseded.append({"cell": cell, "result": res["layers"]["L4"].get("embedder_probe")})
            log(f"rerun {cell}")
            res["layers"]["L4"]["embedder_probe"] = embedder_probe(env, l4_cfg)
        else:
            raise SystemExit(f"cannot re-run cell '{cell}' (not in this run's layers/config)")
    if l1_cfg is not None and "L1" in res["layers"]:
        l1_arms = res["layers"]["L1"]["arms"]
        matrix = R.l1_matrix(l1_arms, l1_cfg.tests)
        res["summary"]["l1_matrix"] = matrix
        res["summary"]["headline"] = R.headline(matrix, l1_arms)
        res["summary"]["l1_violations_total"] = {
            a: sum(sum(r["violations_total"].values()) for r in v["tests"].values())
            for a, v in l1_arms.items()
        }
    res["honesty"] = R.HONESTY
    res["environment"]["falkordb_rerun"] = environment.falkordb_info(env.host, env.port)
    res["run"].setdefault("reruns", []).append(
        {
            "at": iso_utc(),
            "reason": reason,
            "cells": cells,
            "git_commit": environment.git_commit(),
            "superseded": superseded,
        }
    )
    from knewat.crucible.report import render

    path.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8", newline="\n")
    (out_dir / "report.md").write_text(render(res), encoding="utf-8", newline="\n")
    (out_dir.parent / "latest.json").write_text(
        path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
    )
    return out_dir, res
