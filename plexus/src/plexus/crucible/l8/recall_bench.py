"""L8 recall completeness, no LLM (P12): does ``recall`` return the long-horizon facts the L8 tasks need?

Builds the same P store an L8 run starts from (the 20-sprint L2-scale history played through the P-mcp backend
with the ``hash`` embedder, exactly as ``l8.run.run_arm``), then talks to an in-process Plexus MCP server (the real
tool layer: argument defaults, scope resolution, recall) and measures two things:

* **replay**: every ``assert_fact`` / ``add_source`` / ``recall`` the Round A P agents issued, in transcript order,
  with the agents' own arguments. For the recalls made while working on ``t13-reuse-billing-cycle`` (needs the S07
  billing cycle and the S13 API-key header) and ``t16-release-notes`` (needs the S20 release channel) it records
  whether the needed history fact the query asked for came back (:func:`intended_targets`), and per task whether
  any of its recalls found it. No LLM: the queries are the ones the agents actually typed.
* **canonical**: for every sprint S01..S20 and each of five history facts (api_version, database, API-key
  auth_method, billing_cycle, release_channel), two fixed queries (one naming the subject, one paraphrase without
  it) with the tool's *default* arguments, after the seed's S21 writes are in the store. Completeness = targets
  returned / targets asked.

Usage: ``python -m plexus.crucible.l8.recall_bench --port 6366 --label before [--seeds 20261017 ...]``.
Writes ``demo_data/crucible/l8_postfix/recall_bench-<label>.json``. Records no benchmark result by itself.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from plexus.crucible.l2.scale_scenario import Sprint

ROOT = Path(__file__).resolve().parents[4]
RUNS = ROOT / "demo_data" / "crucible" / "l8" / "runs"
OUT = ROOT / "demo_data" / "crucible" / "l8_postfix"
SEEDS = (20261017, 20261018, 20261019, 20261020, 20261021)

S07, S13, S20 = Sprint(7), Sprint(13), Sprint(20)
# label -> (entity name, predicate, a string the fact's value must contain)
TARGETS = {
    "S07 billing cycle": (S07.billing_subject, "billing_cycle", S07.cycle),
    "S13 API-key header": (S13.subject, "auth_method", "X-Core-Key"),
    "S20 release channel": (S20.subject, "release_channel", S20.channel),
}
TASK_TARGETS = {
    "t13-reuse-billing-cycle": ("S07 billing cycle", "S13 API-key header"),
    "t16-release-notes": ("S20 release channel",),
}
ASSERT_ARGS = ("agent_id", "subject", "predicate", "value", "scope", "supersede", "step")


_INTENT = {
    "S07 billing cycle": re.compile(r"bill|bolt|cycle|invoice|s07", re.I),
    "S13 API-key header": re.compile(r"key|header|s13", re.I),
    "S20 release channel": re.compile(r"release|channel|s20", re.I),
}


def intended_targets(task: str, query: str) -> tuple[str, ...]:
    """The needed history facts a recall made during ``task`` is about: the ones its query words point at
    (``billing cycle S07`` -> the S07 fact only), or all of the task's needs when it points at none or several.
    A query is only scored against what it asked for."""
    need = TASK_TARGETS.get(task, ())
    hit = tuple(lab for lab in need if _INTENT[lab].search(query))
    return hit if len(hit) == 1 else need


def _hit(facts: list[dict[str, Any]], target: tuple[str, str, str]) -> bool:
    ent, pred, val = target
    return any(
        f.get("entity") == ent
        and f.get("predicate") == pred
        and val.lower() in str(f.get("value", "")).lower()
        for f in facts
    )


def canonical_targets() -> list[dict[str, Any]]:
    """(label, entity, predicate, value-substring, named query, paraphrase query) for S01..S20 x 5 facts."""
    out = []
    for n in range(1, 21):
        sp = Sprint(n)
        rows = [
            ("api_version", sp.subject, "api_version", sp.v_new, "API version"),
            ("database", sp.subject, "database", sp.db, "database"),
            (
                "apikey_header",
                sp.subject,
                "auth_method",
                sp.apikey.split(" in ", 1)[1].split()[0],
                "API-key header",
            ),
            ("billing_cycle", sp.billing_subject, "billing_cycle", sp.cycle, "billing cycle"),
            ("release_channel", sp.subject, "release_channel", sp.channel, "release channel"),
        ]
        for kind, ent, pred, val, words in rows:
            out.append(
                {
                    "sprint": sp.tag,
                    "kind": kind,
                    "target": (ent, pred, val),
                    "named": f"{ent} {words}",
                    "paraphrase": f"{words} decided in sprint {sp.tag}",
                }
            )
    return out


def transcript_events(seed: int) -> list[dict[str, Any]]:
    """Ordered plexus tool calls of the seed's P run, each with its task id and (for add_source) old result id."""
    tdir = RUNS / str(seed) / "P" / "transcripts"
    events: list[dict[str, Any]] = []
    for f in sorted(tdir.glob("*.jsonl")):
        task = next((t for t in TASK_TARGETS if t in f.name), "")
        pending: dict[str, dict[str, Any]] = {}
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            msg = ev.get("message") or {}
            content = msg.get("content") if isinstance(msg.get("content"), list) else []
            if ev.get("type") == "assistant":
                for b in content:
                    if b.get("type") == "tool_use" and str(b.get("name", "")).startswith("mcp__plexus__"):
                        e = {"tool": b["name"][len("mcp__plexus__") :], "args": b["input"], "task": task,
                             "file": f.name}  # fmt: skip
                        events.append(e)
                        pending[b["id"]] = e
            elif ev.get("type") == "user":
                for b in content:
                    if (
                        isinstance(b, dict)
                        and b.get("type") == "tool_result"
                        and b.get("tool_use_id") in pending
                    ):
                        e = pending.pop(b["tool_use_id"])
                        c = b.get("content")
                        text = c[0].get("text", "") if isinstance(c, list) and c else str(c or "")
                        try:
                            e["result"] = json.loads(text)
                        except ValueError:
                            e["result"] = None
    return events


async def _bench_seed(
    seed: int, port: int, canonical: list[dict[str, Any]], scope: str | None = None, embedder: str = "hash"
) -> dict[str, Any]:
    from mcp import Client
    from plexus.crucible.api import BackendSpec
    from plexus.crucible.backends import open_backend
    from plexus.crucible.l2.scale_scenario import play_scale
    from plexus.embed import get_embedder
    from plexus.graph.client import GraphClient
    from plexus.graph.schema import apply_schema
    from plexus.graph.tenancy import graph_name
    from plexus.mcp.runtime import Runtime
    from plexus.mcp.server import build_server

    tenant = f"l8rb_{seed}_{uuid.uuid4().hex[:6]}"
    gc = GraphClient(host="127.0.0.1", port=port)
    apply_schema(gc, graph_name(tenant))
    t0 = time.time()
    b = open_backend(
        BackendSpec(arm="P-mcp", tenant=tenant, root="", host="127.0.0.1", port=port, embedder=embedder)
    )
    play_scale(b, 20)
    b.close()
    hist_s = time.time() - t0
    if embedder == "hash":
        emb = get_embedder("hash")
    else:  # the server's embedder (BGE with its query form)
        from plexus.mcp.embedding import make_embedder

        os.environ["PLEXUS_EMBEDDER"] = embedder
        emb = make_embedder()
    server = build_server(Runtime(client=gc, embedder=emb, stdio_tenant=tenant))
    src_map: dict[str, str] = {}
    replay: list[dict[str, Any]] = []
    errors = 0
    try:
        async with Client(server) as c:

            async def call(tool: str, args: dict[str, Any]) -> dict[str, Any] | None:
                nonlocal errors
                res = await c.call_tool(tool, args)
                if res.is_error:
                    errors += 1
                    return None
                return json.loads(res.content[0].text)

            for e in transcript_events(seed):
                a = dict(e["args"])
                if e["tool"] == "add_source":
                    got = await call("add_source", a)
                    old = (e.get("result") or {}).get("source_id")
                    if got and old:
                        src_map[old] = got["source_id"]
                elif e["tool"] == "assert_fact":
                    args = {k: a[k] for k in ASSERT_ARGS if k in a}
                    if a.get("source_id") in src_map:
                        args["source_id"] = src_map[a["source_id"]]
                    await call("assert_fact", args)
                elif e["tool"] == "recall":
                    if scope is not None:
                        a["scope"] = scope
                    got = await call("recall", a)
                    facts = (got or {}).get("facts", [])
                    need = intended_targets(e["task"], str(a.get("query", "")))
                    replay.append(
                        {
                            "file": e["file"],
                            "task": e["task"],
                            "query": a.get("query"),
                            "args": {k: v for k, v in a.items() if k not in ("agent_id", "query", "step")},
                            "returned": len(facts),
                            "truncated": (got or {}).get("truncated"),
                            "found": {lab: _hit(facts, TARGETS[lab]) for lab in need},
                        }
                    )
            canon = []
            for row in canonical:
                for style in ("named", "paraphrase"):
                    args = {"agent_id": "bench", "query": row[style]}
                    if scope is not None:
                        args["scope"] = scope
                    got = await call("recall", args)
                    facts = (got or {}).get("facts", [])
                    canon.append(
                        {
                            "sprint": row["sprint"],
                            "kind": row["kind"],
                            "style": style,
                            "query": row[style],
                            "returned": len(facts),
                            "found": _hit(facts, row["target"]),
                            "rank": next(
                                (i + 1 for i, f in enumerate(facts) if _hit([f], row["target"])), None
                            ),
                        }
                    )
    finally:
        gc.delete_graph(graph_name(tenant))
        gc.close()
    return {"seed": seed, "history_seconds": round(hist_s, 1), "tool_errors": errors, "replay": replay,
            "canonical": canon}  # fmt: skip


def summarise(seeds: list[dict[str, Any]]) -> dict[str, Any]:
    calls = [r for s in seeds for r in s["replay"] if r["found"]]  # recalls made during t13 / t16
    per_call = {"calls": len(calls), "target_hits": 0, "target_asks": 0}
    task_found: dict[str, list[bool]] = {}
    for s in seeds:
        by_task: dict[tuple[str, str], bool] = {}
        for r in s["replay"]:
            want = intended_targets(r["task"], str(r["query"] or ""))
            for lab, ok in r["found"].items():
                if lab not in want:
                    continue
                per_call["target_asks"] += 1
                per_call["target_hits"] += bool(ok)
                by_task[(r["task"], lab)] = by_task.get((r["task"], lab), False) or bool(ok)
        for (_task, lab), ok in by_task.items():
            task_found.setdefault(lab, []).append(ok)
    canon = [r for s in seeds for r in s["canonical"]]

    def frac(rows: list[dict[str, Any]]) -> str:
        return f"{sum(r['found'] for r in rows)}/{len(rows)}"

    by_kind = {
        k: {
            st: frac([r for r in canon if r["kind"] == k and r["style"] == st])
            for st in ("named", "paraphrase")
        }
        for k in sorted({r["kind"] for r in canon})
    }
    return {
        "replay_per_call": per_call,
        "replay_needed_fact_found_by_any_call_of_task": {
            lab: f"{sum(v)}/{len(v)}" for lab, v in sorted(task_found.items())
        },
        "canonical_all": frac(canon),
        "canonical_named": frac([r for r in canon if r["style"] == "named"]),
        "canonical_paraphrase": frac([r for r in canon if r["style"] == "paraphrase"]),
        "canonical_by_kind": by_kind,
        "canonical_mean_returned": round(sum(r["returned"] for r in canon) / max(len(canon), 1), 1),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="l8-recall-bench")
    ap.add_argument("--port", type=int, default=6366)
    ap.add_argument("--label", default=None)
    ap.add_argument("--seeds", type=int, nargs="*", default=list(SEEDS))
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument(
        "--scope", default=None, help="override every recall's scope (ablation); default: as called"
    )
    ap.add_argument("--embedder", default="hash", help="hash (as L8) or fastembed (BGE, the product default)")
    ap.add_argument(
        "--resummarise", type=Path, default=None, help="recompute the summary of an existing file"
    )
    a = ap.parse_args(argv)
    if a.resummarise:
        rec = json.loads(a.resummarise.read_text(encoding="utf-8"))
        rec["summary"] = summarise(rec["seeds"])
        a.resummarise.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps(rec["summary"], indent=1))
        return 0
    if not a.label:
        ap.error("--label is required")
    canonical = canonical_targets()
    seeds = []
    for seed in a.seeds:
        r = asyncio.run(_bench_seed(seed, a.port, canonical, a.scope, a.embedder))
        print(f"seed {seed}: replay calls {len(r['replay'])}, tool errors {r['tool_errors']}", flush=True)
        seeds.append(r)
    from plexus.crucible.l8.run import git_state

    rec = {"kind": "crucible-l8-recall-bench", "label": a.label, "scope_override": a.scope, "embedder": a.embedder,
           "bge_query_prefix": os.environ.get("PLEXUS_BGE_QUERY_PREFIX", "on"), "git": git_state(),
           "summary": summarise(seeds),
           "seeds": seeds}  # fmt: skip
    a.out.mkdir(parents=True, exist_ok=True)
    path = a.out / f"recall_bench-{a.label}.json"
    path.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(rec["summary"], indent=1))
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
