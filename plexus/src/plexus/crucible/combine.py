"""Build the combined results file the View's Results page reads: L1 + L4 + ablation, plus L2 and L2_scale.

    python -m plexus.crucible.combine                 # -> crucible/results/latest-all.json (the defaults below)
    python -m plexus.crucible.combine --check         # exit 1 if the committed latest-all.json is not what this would write

``crucible all`` writes (and overwrites) ``results/latest.json`` with L1, L4 and the ablation; the L2 and L2-scale runs write
their own ``results.json`` under ``demo_data/crucible/``. This module adds ``layers["L2"]`` (via
``plexus.crucible.l2.run.merge_into``) and ``layers["L2_scale"]`` to a copy of the first, never touching the inputs.
The result is deterministic, so ``--check`` (and a test) can prove the committed file is exactly the merge of its parts.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

from plexus.crucible.l2.run import DEMO_DATA, merge_into

RESULTS_DIR = Path(__file__).resolve().parent / "results"
DEFAULT_BASE = RESULTS_DIR / "latest.json"
DEFAULT_L2 = DEMO_DATA / "l2" / "latest-full.json"
DEFAULT_L2_SCALE = DEMO_DATA / "l2_scale" / "latest-full.json"
DEFAULT_OUT = RESULTS_DIR / "latest-all.json"


def merge_l2_scale(base: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
    """``base`` with the L2-scale layer, its arm info, summary lines and honesty notes added."""
    out = copy.deepcopy(base)
    # the run's honesty notes travel with the layer too (verbatim), so the Results page can print them inside its section
    out.setdefault("layers", {})["L2_scale"] = {**doc["layers"]["L2_scale"], "honesty": list(doc["honesty"])}
    run_layers = out.setdefault("run", {}).setdefault("layers", [])
    if "L2_scale" not in run_layers:
        run_layers.append("L2_scale")
    out.setdefault("config", {})["l2_scale"] = doc["config"]["l2_scale"]
    for arm, info in doc["arms"].items():
        out.setdefault("arms", {}).setdefault(arm, info)
    cfg_arms = out["config"].setdefault("arms", [])
    for arm in doc["config"]["arms"]:
        if arm not in cfg_arms:
            cfg_arms.append(arm)
    summ = out.setdefault("summary", {})
    summ["l2_scale_accuracy_pct"] = doc["summary"]["l2_scale_accuracy_pct"]
    summ["headline"] = [*summ.get("headline", []), *doc["summary"]["headline"]]
    hon = out.setdefault("honesty", [])
    hon += [h for h in doc["honesty"] if h not in hon]
    return out


def combine(base: Path, l2: Path | None, l2_scale: Path | None) -> dict[str, Any]:
    doc = json.loads(base.read_text(encoding="utf-8"))
    if l2 is not None:
        doc = merge_into(doc, json.loads(l2.read_text(encoding="utf-8")))
    if l2_scale is not None:
        doc = merge_l2_scale(doc, json.loads(l2_scale.read_text(encoding="utf-8")))
    return doc


def render(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m plexus.crucible.combine", description=__doc__.split("\n")[0])
    ap.add_argument("--base", type=Path, default=DEFAULT_BASE, help="L1 + L4 + ablation file (crucible all)")
    ap.add_argument("--l2", type=Path, default=DEFAULT_L2, help="L2 results.json ('none' to skip)")
    ap.add_argument(
        "--l2-scale", type=Path, default=DEFAULT_L2_SCALE, help="L2-scale results.json ('none' to skip)"
    )
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="compare with --out instead of writing it")
    a = ap.parse_args(argv)
    skip = Path("none")
    text = render(combine(a.base, None if a.l2 == skip else a.l2, None if a.l2_scale == skip else a.l2_scale))
    if a.check:
        same = a.out.is_file() and a.out.read_text(encoding="utf-8") == text
        print(
            f"{a.out}: {'up to date' if same else 'DIFFERS from the merge of its parts; rerun without --check'}"
        )
        return 0 if same else 1
    a.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
