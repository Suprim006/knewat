"""Build the combined results file the View's Results page reads: L1 + L4 + ablation, plus L2, L2_scale, B1h, C7 extended and L6.

    python -m knewat.crucible.combine                 # -> crucible/results/latest-all.json (every layer below)
    python -m knewat.crucible.combine --b1h none --c7x none --l6 none   # the pre-P9 file (L1, L4, ablation, L2, L2-scale)
    python -m knewat.crucible.combine --check         # exit 1 if the committed latest-all.json is not what this would write

``crucible all`` writes (and overwrites) ``results/latest.json`` with L1, L4 and the ablation; the L2 and L2-scale runs write
their own ``results.json`` under ``demo_data/crucible/``. This module adds ``layers["L2"]`` (via
``knewat.crucible.l2.run.merge_into``) and ``layers["L2_scale"]`` to a copy of the first, never touching the inputs.
The result is deterministic, so ``--check`` (and a test) can prove the committed file is exactly the merge of its parts.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

from knewat.crucible.l2.run import DEMO_DATA, merge_into

RESULTS_DIR = Path(__file__).resolve().parent / "results"
DEFAULT_BASE = RESULTS_DIR / "latest.json"
DEFAULT_L2 = DEMO_DATA / "l2" / "latest-full.json"
DEFAULT_L2_SCALE = DEMO_DATA / "l2_scale" / "latest-full.json"
DEFAULT_OUT = RESULTS_DIR / "latest-all.json"
DEFAULT_B1H = DEMO_DATA / "b1h" / "latest.json"
DEFAULT_L6 = DEMO_DATA / "l6"
DEFAULT_C7X = DEMO_DATA / "c7x_results.json"


def _mark_layer(doc: dict[str, Any], name: str) -> None:
    run_layers = doc.setdefault("run", {}).setdefault("layers", [])
    if name not in run_layers:
        run_layers.append(name)


def merge_l2_scale(base: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
    """``base`` with the L2-scale layer, its arm info, summary lines and honesty notes added."""
    out = copy.deepcopy(base)
    # the run's honesty notes travel with the layer too (verbatim), so the Results page can print them inside its section
    out.setdefault("layers", {})["L2_scale"] = {**doc["layers"]["L2_scale"], "honesty": list(doc["honesty"])}
    _mark_layer(out, "L2_scale")
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


def merge_b1h(base: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
    """``base`` with the B1h control (hand-written SQL on L2 and L2-scale) as ``layers["B1h"]``."""
    out = copy.deepcopy(base)
    out.setdefault("layers", {})["B1h"] = {
        "title": "B1h: hand-written SQL control for L2 and L2-scale",
        "run": doc["run"], "answerer": doc["answerer"], "code_size": doc["code_size"], "layers": doc["layers"], "honesty": doc["honesty"],
    }  # fmt: skip
    _mark_layer(out, "B1h")
    return out


def merge_c7x(base: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
    """``base`` with the extended duplicate corpus (C7x, P9-c) as ``layers["C7x"]``: per arm the headline metrics, and the
    per-category outcomes of the Knewat service arm (not the per-pair rows: those stay in ``c7x_results.json``)."""
    out = copy.deepcopy(base)
    arms = {}
    for name, a in doc["arms"].items():
        arms[name] = {"violations": a["violations"], "metrics": a["metrics"]}
    p = doc["arms"]["P"]["details"]
    out.setdefault("layers", {})["C7x"] = {
        "title": "C7 extended: does the duplicate rule merge two different statements?",
        "note": doc["note"],
        "arms": arms,
        "by_category": p["by_category"],
        "false_merge_upper_95": p["false_merge_upper_95"],
        "targets": {
            "heavy_auto_pct": 75.0,
            "heavy_surfaced_pct": 95.0,
            "other_merge_categories_auto_pct": 100.0,
        },
    }
    _mark_layer(out, "C7x")
    return out


def merge_l6(base: dict[str, Any], layer: dict[str, Any]) -> dict[str, Any]:
    """``base`` with the L6 beat-SQL layer (``knewat.crucible.l6.run.build_layer``) as ``layers["L6"]``."""
    out = copy.deepcopy(base)
    out.setdefault("layers", {})["L6"] = layer
    _mark_layer(out, "L6")
    return out


def combine(
    base: Path,
    l2: Path | None,
    l2_scale: Path | None,
    b1h: Path | None = None,
    l6: Path | None = None,
    c7x: Path | None = None,
) -> dict[str, Any]:
    """Every layer the Results page draws; ``None`` leaves a layer out (the CLI defaults include all of them)."""
    doc = json.loads(base.read_text(encoding="utf-8"))
    if l2 is not None:
        doc = merge_into(doc, json.loads(l2.read_text(encoding="utf-8")))
    if l2_scale is not None:
        doc = merge_l2_scale(doc, json.loads(l2_scale.read_text(encoding="utf-8")))
    if b1h is not None:
        doc = merge_b1h(doc, json.loads(b1h.read_text(encoding="utf-8")))
    if c7x is not None:
        doc = merge_c7x(doc, json.loads(c7x.read_text(encoding="utf-8")))
    if l6 is not None:
        from knewat.crucible.l6.run import build_layer

        doc = merge_l6(doc, build_layer(l6))
    return doc


def render(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m knewat.crucible.combine", description=__doc__.split("\n")[0])
    ap.add_argument("--base", type=Path, default=DEFAULT_BASE, help="L1 + L4 + ablation file (crucible all)")
    ap.add_argument("--l2", type=Path, default=DEFAULT_L2, help="L2 results.json ('none' to skip)")
    ap.add_argument(
        "--l2-scale", type=Path, default=DEFAULT_L2_SCALE, help="L2-scale results.json ('none' to skip)"
    )
    ap.add_argument(
        "--b1h", type=Path, default=DEFAULT_B1H, help="B1h results.json, layers.B1h ('none' to skip)"
    )
    ap.add_argument(
        "--c7x",
        type=Path,
        default=DEFAULT_C7X,
        help="C7-extended c7x_results.json, layers.C7x ('none' to skip)",
    )
    ap.add_argument(
        "--l6",
        type=Path,
        default=DEFAULT_L6,
        help="demo_data/crucible/l6 directory, layers.L6 ('none' to skip)",
    )
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="compare with --out instead of writing it")
    a = ap.parse_args(argv)
    skip = Path("none")
    text = render(
        combine(
            a.base,
            None if a.l2 == skip else a.l2,
            None if a.l2_scale == skip else a.l2_scale,
            None if a.b1h == skip else a.b1h,
            None if a.l6 == skip else a.l6,
            None if a.c7x == skip else a.c7x,
        )
    )
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
