"""L5 runner: results.json, the pass criteria of the pre-registration, and report.md."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from plexus.crucible.l5.forgetting import run_forgetting
from plexus.crucible.l5.staleness import run_staleness
from plexus.crucible.util import iso_utc, run_stamp
from plexus.embed import get_embedder
from plexus.graph.client import GraphClient

DEFAULT_OUT = Path(__file__).resolve().parents[4] / "demo_data" / "crucible" / "l5"


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _ms(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def criteria(res: dict[str, Any], margin: float = 0.02) -> list[dict[str, Any]]:
    """The pass criteria fixed in the pre-registration, evaluated on a result (``margin``: the recall@5 tolerance)."""
    out: list[dict[str, Any]] = []
    if "staleness" in res:
        arms = res["staleness"]["arms"]
        for a in ("S", "F"):
            n = arms[a]["stale_returned_unflagged"]
            out.append({"id": f"L5a unflagged = 0 ({a})", "hard": True, "ok": n == 0, "value": n})
    if "forgetting" in res:
        f = res["forgetting"]
        m, sw = f["modes"], f["sweep"]
        tol = 1e-9
        if "on" in m and "on+sweep" in m:
            loss_on, loss_sw = m["on"]["critical_probe_loss"], m["on+sweep"]["critical_probe_loss"]
            out.append(
                {
                    "id": "L5b critical-probe loss = 0 (on, on+sweep)",
                    "hard": True,
                    "ok": loss_on == 0 and loss_sw == 0,
                    "value": [loss_on, loss_sw],
                }
            )
        if "on+sweep" in m:
            out.append(
                {
                    "id": "L5b no critical fact moved to dormant",
                    "hard": True,
                    "ok": sw["moved_by_class"]["critical"] == 0 and sw["dry_run_critical_candidates"] == 0,
                    "value": sw["moved_by_class"]["critical"],
                }
            )
            out.append(
                {
                    "id": "L5b fact count unchanged by the sweep",
                    "hard": True,
                    "ok": sw["fact_nodes_before"] == sw["fact_nodes_after"],
                    "value": [sw["fact_nodes_before"], sw["fact_nodes_after"]],
                }
            )
        if "on" in m and "off" in m:
            r_off = m["off"]["recall"]["all"]["recall@5"]
            r_on = m["on"]["recall"]["all"]["recall@5"]
            out.append(
                {
                    "id": f"L5b recall@5 of 'on' within {margin:g} of 'off'",
                    "hard": False,
                    "ok": r_on >= r_off - margin - tol,
                    "value": [r_off, r_on],
                }
            )
        if "on" in m and "on+sweep" in m and "off" in m:
            n_off = m["off"]["noise_share"]
            best = min(m["on"]["noise_share"], m["on+sweep"]["noise_share"])
            out.append(
                {"id": "L5b noise share reduced", "hard": False, "ok": best < n_off, "value": [n_off, best]}
            )

        def r(mode: str, k: int = 1) -> float:
            return m[mode]["recall"]["all"][f"recall@{k}"]

        if "sep" in m:
            s1 = r("sep")
            out.append(
                {"id": "L5b-D013 sep recall@1 >= 0.90", "hard": False, "ok": s1 >= 0.90 - tol, "value": [s1]}
            )
            out.append(
                {
                    "id": "L5b-D013 sep recall@1 >= 0.85 (falsification floor)",
                    "hard": True,
                    "ok": s1 >= 0.85 - tol,
                    "value": [s1],
                }
            )
            if "off" in m:
                out.append(
                    {
                        "id": "L5b-D013 sep recall@5 >= off - 0.005",
                        "hard": False,
                        "ok": r("sep", 5) >= r("off", 5) - 0.005 - tol,
                        "value": [r("off", 5), r("sep", 5)],
                    }
                )
            loss = m["sep"].get("critical_probe_loss")
            out.append(
                {
                    "id": "L5b-D013 sep critical loss = 0",
                    "hard": True,
                    "ok": loss == 0,
                    "value": loss,
                }
            )
        if "sep+add" in m:
            sa = m["sep+add"]
            if "sep" in m:
                out.append(
                    {
                        "id": "L5b-D013 sep+add recall@1 >= sep - 0.01",
                        "hard": True,
                        "ok": r("sep+add") >= r("sep") - 0.01 - tol,
                        "value": [r("sep"), r("sep+add")],
                    }
                )
                out.append(
                    {
                        "id": "L5b-D013 sep+add recall@5 >= sep - 0.005",
                        "hard": False,
                        "ok": r("sep+add", 5) >= r("sep", 5) - 0.005 - tol,
                        "value": [r("sep", 5), r("sep+add", 5)],
                    }
                )
            ns = sa["noise_share"]
            out.append(
                {
                    "id": "L5b-D013 sep+add noise share <= 0.155",
                    "hard": False,
                    "ok": ns is not None and ns <= 0.155 + tol,
                    "value": ns,
                }
            )
            ab = sa.get("ranked_above_target", {})
            ch = ab.get("critical", 0) + ab.get("hot", 0)
            out.append(
                {
                    "id": "L5b-D013 sep+add critical+hot above target <= 5",
                    "hard": False,
                    "ok": ch <= 5,
                    "value": ch,
                }
            )
            if f["config"].get("burst"):
                hac = sa.get("hot_above_cold")
                out.append(
                    {
                        "id": "L5b-D013 burst: hot above cold target <= 1% (sep+add)",
                        "hard": False,
                        "ok": hac is not None and hac <= 0.01 + tol,
                        "value": hac,
                    }
                )
        if "kw-fix" in m:
            out.append(
                {
                    "id": "L5b-D013 kw-fix recall@1 (report only)",
                    "hard": False,
                    "ok": True,
                    "value": r("kw-fix"),
                }
            )
    return out


def run_all(
    client: GraphClient,
    embedder_kind: str | None,
    out_root: Path,
    *,
    staleness: bool = True,
    forgetting: bool = True,
    sprints: int = 20,
    noise: int = 5,
    modules: int = 12,
    funcs: int = 5,
    commits: int = 20,
    margin: float = 0.02,
    tag: str = "",
    modes: Sequence[str] = ("off", "on", "on+sweep"),
    burst: bool = False,
) -> Path:
    embedder = get_embedder(embedder_kind)
    started = time.time()
    res: dict[str, Any] = {
        "layer": "L5",
        "started_at": iso_utc(started),
        "embedder": type(embedder).__name__,
        "git_commit": os.environ.get("CRUCIBLE_GIT_COMMIT") or _git_head(),
        "llm_calls": 0,
    }
    if staleness:
        with tempfile.TemporaryDirectory(prefix="plexus-l5-") as tmp:
            res["staleness"] = run_staleness(client, embedder, Path(tmp), modules, funcs, commits)
    if forgetting:
        res["forgetting"] = run_forgetting(client, embedder, sprints, noise, modes=modes, burst=burst)
    res["criteria"] = criteria(res, margin)
    res["seconds"] = round(time.time() - started, 1)
    out = out_root / (run_stamp(started) + (f"-{tag}" if tag else ""))
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(res, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "report.md").write_text(render_report(res), encoding="utf-8")
    return out


def _git_head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).parent,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def render_report(res: dict[str, Any]) -> str:
    L: list[str] = [
        "# Crucible L5 results",
        "",
        f"Run {res['started_at']}, code {res['git_commit'] or 'unknown'}, embedder {res['embedder']}, LLM calls: {res['llm_calls']}.",
        'Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".',
        "",
    ]
    if "staleness" in res:
        s = res["staleness"]
        r = s["repo"]
        L += [
            "## L5a: staleness",
            "",
            f"{r['modules']} modules, {r['functions']} functions/facts, {r['change_commits']} change commits "
            f"({', '.join(r['kinds'])}); {r['truth_facts_total']} (commit, fact) pairs changed in total.",
            "",
            "| Arm | TP | FP | FN | precision | recall | stale returned unflagged | stale not in top 3 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        names = {"S": "S symbol-level anchors", "F": "F file-level anchors", "N": "N no anchors (baseline)"}
        for a, x in s["arms"].items():
            L.append(
                f"| {names[a]} | {x['tp']} | {x['fp']} | {x['fn']} | {_pct(x['precision'])} | {_pct(x['recall'])} | "
                f"{x['stale_returned_unflagged']} | {x['stale_not_returned_in_top3']} |"
            )
        L += [
            "",
            "Facts flagged per edit kind (all arms):",
            "",
            "| Kind | " + " | ".join(s["arms"]) + " |",
            "|---|" + "---|" * len(s["arms"]),
        ]
        for k in dict.fromkeys(r["kinds"]):
            L.append(
                f"| {k} | "
                + " | ".join(str(s["arms"][a]["flagged_by_kind"].get(k, 0)) for a in s["arms"])
                + " |"
            )
        L.append("")
    if "forgetting" in res:
        f = res["forgetting"]
        c = f["config"]
        L += [
            "## L5b: forgetting",
            "",
            f"{c['sprints']} sprints, {f['history']['real_active_facts']} real active facts "
            f"(critical {f['classes']['critical']}, hot {f['classes']['hot']}, cold {f['classes']['cold']}), "
            f"{f['noise_facts']} noise facts ({c['noise_per_subject']} per subject), {c['days']} simulated days, "
            f"{f['reads']['read_edges']} simulated READ edges.",
            "",
            "| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for name, m in f["modes"].items():
            rc = m["recall"]
            L.append(
                f"| {name} | {_pct(rc['all']['recall@1'])} | {_pct(rc['all']['recall@3'])} | {_pct(rc['all']['recall@5'])} | "
                f"{_pct(rc.get('critical', {}).get('recall@5'))} | {_pct(rc.get('hot', {}).get('recall@5'))} | "
                f"{_pct(rc.get('cold', {}).get('recall@5'))} | {_pct(m['noise_share'])} | {m['chars_per_recall']:.0f} | "
                f"{m.get('critical_probe_loss', '-')} | {m.get('above_same_entity', '-')} | "
                f"{m.get('above_other_entity', '-')} | {_pct(m.get('hot_above_cold'))} | {_ms(m.get('entity_read_ms'))} |"
            )
        L += [
            "",
            "Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the "
            "target (on a miss, of all rows returned), summed over all probes:",
            "",
            "| Mode | noise | hot | critical | cold | other |",
            "|---|---|---|---|---|---|",
        ]
        for name, m in f["modes"].items():
            ab = m.get("ranked_above_target", {})
            L.append(
                f"| {name} | "
                + " | ".join(str(ab.get(k, 0)) for k in ("noise", "hot", "critical", "cold", "other"))
                + " |"
            )
        L += [
            "",
            "Relevance gap between the first and second returned row (cosine distance), per mode:",
            "",
            "| Mode | n | p10 | p25 | p50 | p75 | p90 |",
            "|---|---|---|---|---|---|---|",
        ]
        for name, m in f["modes"].items():
            g = m.get("gap12") or {}
            L.append(
                f"| {name} | {g.get('n', 0)} | "
                + " | ".join(
                    "n/a" if g.get(k) is None else f"{g[k]:.4f}" for k in ("p10", "p25", "p50", "p75", "p90")
                )
                + " |"
            )
        sw = f["sweep"]
        L += [
            "",
            f"Sweep (real, `on+sweep`): {sw['moved_total']} facts moved to dormant: {sw['moved_by_class']}; "
            f"critical facts among the dry-run candidates: {sw['dry_run_critical_candidates']}; "
            f"Fact nodes before/after: {sw['fact_nodes_before']}/{sw['fact_nodes_after']}.",
            "",
        ]
    L += [
        "## Pass criteria (fixed in the pre-registration)",
        "",
        "| Criterion | hard | result | value |",
        "|---|---|---|---|",
    ]
    for k in res["criteria"]:
        L.append(
            f"| {k['id']} | {'yes' if k['hard'] else 'no'} | {'PASS' if k['ok'] else 'FAIL'} | {k['value']} |"
        )
    L.append("")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="plexus.crucible.l5", description="Crucible L5: staleness and forgetting (no LLM)"
    )
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--only", choices=("staleness", "forgetting"))
    p.add_argument("--sprints", type=int, default=20)
    p.add_argument("--noise", type=int, default=5, help="noise facts per subject (5 primary, 15 stress)")
    p.add_argument(
        "--margin", type=float, default=0.02, help="recall@5 tolerance of the non-inferiority criterion"
    )
    p.add_argument(
        "--modes",
        default="off,on,on+sweep",
        help="comma-separated forgetting modes (see forgetting.MODE_TABLE)",
    )
    p.add_argument(
        "--burst", action="store_true", help="hot facts read in one burst at day 45 instead of daily"
    )
    p.add_argument("--tag", default="", help="suffix of the result directory (e.g. floor09)")
    p.add_argument("--embedder", choices=("fastembed", "hash"))
    p.add_argument("--host", help="FalkorDB host (default $FALKORDB_HOST or 127.0.0.1)")
    p.add_argument("--port", type=int, help="FalkorDB port (default $FALKORDB_PORT or 6379)")
    a = p.parse_args(argv)
    client = GraphClient(host=a.host, port=a.port)
    try:
        out = run_all(
            client,
            a.embedder,
            a.out,
            staleness=a.only in (None, "staleness"),
            forgetting=a.only in (None, "forgetting"),
            sprints=a.sprints,
            noise=a.noise,
            margin=a.margin,
            tag=a.tag,
            modes=[x.strip() for x in a.modes.split(",") if x.strip()],
            burst=a.burst,
        )
    finally:
        client.close()
    print(f"wrote {out}")
    print((out / "report.md").read_text(encoding="utf-8"))
    res = json.loads((out / "results.json").read_text(encoding="utf-8"))
    return 0 if all(k["ok"] for k in res["criteria"] if k["hard"]) else 1


if __name__ == "__main__":
    sys.exit(main())
