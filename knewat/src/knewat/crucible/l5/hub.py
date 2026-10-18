"""L5b hub variant (plan §5.3; CROSS_CHECK §3.2): one entity with 200 active facts of distinct predicates, probes
that name the entity and the predicate. Pre-registered in docs/BASELINE.md ("Predicate cue pre-registration").

The question the variant decides: can the fan term separate the facts of ONE named entity? A single entity cue
lifts every fact of the hub equally, so the answer would rest on relevance alone; the two-cue context term adds
a predicate cue that the asked fact alone matches.

World (seed 20261016): one scope; the hub ``Atlas Core Platform`` with ``HUB_FACTS`` facts whose predicates are
distinct two-word ``w1_w2`` names; ``N_OTHERS`` ordinary entities (two-word names, disjoint words) with
``FACTS_PER_OTHER`` facts each, predicates drawn from the same pool (so a predicate's fan is about 2, not 1).
Values never repeat the predicate's or the entity's words (the full-text keyword path finds nothing; the vector
seeds, the §3.3 union and the cues do the work). No reads are simulated (forgetting is off in every arm).

Arms (forgetting off): ``off`` (relevance only) and ``sep`` (the two-cue term, shipped default).
"""

from __future__ import annotations

import random
import statistics
import time
import uuid
from typing import Any

from knewat.activation import Settings
from knewat.crucible.l5.forgetting import _Recording, virtual_now
from knewat.embed import Embedder
from knewat.engram import Engram
from knewat.graph.client import GraphClient
from knewat.graph.schema import apply_schema
from knewat.graph.tenancy import graph_name

SEED = 20261016
HUB_NAME = "Atlas Core Platform"
HUB_FACTS = 200
N_OTHERS = 40
FACTS_PER_OTHER = 5
KS = (1, 5)
PRED_A = (
    "billing", "deploy", "cache", "audit", "retry", "backup", "schema", "session", "quota", "token", "index",
    "metric", "alert", "queue", "batch", "export", "import", "replica", "shard", "region",
)  # fmt: skip
PRED_B = ("cycle", "window", "owner", "policy", "limit", "budget", "target", "format", "driver", "mode")
OTHER_A = ("harbor", "meadow", "copper", "willow", "ember", "granite", "lantern", "orchid")
OTHER_B = ("ledger", "router", "vault", "beacon", "courier")
VERBS = ("pinned", "moved", "kept", "set", "rotated", "frozen", "raised", "lowered")
NOUNS = ("tuesday", "quarter", "midnight", "sprint", "friday", "release", "review", "handover")
ARMS: dict[str, tuple[Settings, bool]] = {  # name -> (settings, separation)
    "off": (Settings(), False),
    "sep": (Settings(), True),
}


def _value(rng: random.Random) -> str:
    return f"{rng.choice(VERBS)} to {rng.randrange(1000, 9999)} on {rng.choice(NOUNS)}"


def build_world(eng: Engram, scope_id: str, rng: random.Random, now: int) -> dict[str, Any]:
    """Assert the hub's facts and the ordinary entities' facts. Returns the probes and the predicate fans."""
    preds = [f"{a}_{b}" for a in PRED_A for b in PRED_B][:HUB_FACTS]
    assert len(preds) == HUB_FACTS
    probes: list[dict[str, str]] = []
    for i, p in enumerate(preds):
        fid = eng.assert_fact(HUB_NAME, p, _value(rng), scope_id, "hub-agent", now=now - 10_000 + i)[
            "fact_id"
        ]
        probes.append({"fact_id": fid, "predicate": p, "query": f"{HUB_NAME} {p}"})
    names = [f"{a} {b}" for a in OTHER_A for b in OTHER_B][:N_OTHERS]
    assert len(names) == N_OTHERS
    fan: dict[str, int] = dict.fromkeys(preds, 1)
    j = 0
    for name in names:
        for p in rng.sample(preds, FACTS_PER_OTHER):
            eng.assert_fact(name, p, _value(rng), scope_id, "hub-agent", now=now - 5_000 + j)
            fan[p] += 1
            j += 1
    return {"probes": probes, "predicate_fan": fan, "hub_fact_ids": {p["fact_id"] for p in probes}}


def _measure(eng: Engram, probes: list[dict[str, str]], hub_ids: set[str], settings: Settings, sep: bool,
             recorder: _Recording) -> dict[str, Any]:  # fmt: skip
    hits = {k: 0 for k in KS}
    hub_above = hub_in_top5 = 0
    added: list[int] = []
    ranks: list[int | None] = []
    probe_ms: list[float] = []
    stmts: list[int] = []
    for p in probes:
        recorder.reset()
        t0 = time.perf_counter()
        rows, meta = eng.recall_with_meta(
            p["query"], p["scope_id"], k=max(KS), budget_chars=20_000, forgetting=False, separation=sep,
            settings=settings,
        )  # fmt: skip
        probe_ms.append((time.perf_counter() - t0) * 1000)
        stmts.append(recorder.statements)
        added.append(int(meta.get("entity_facts_added") or 0))
        ids = [r["fact_id"] for r in rows]
        rank = ids.index(p["fact_id"]) if p["fact_id"] in ids else None
        ranks.append(rank)
        for k in KS:
            hits[k] += int(rank is not None and rank < k)
        above = ids[: rank if rank is not None else len(ids)]
        hub_above += int(any(x in hub_ids for x in above))
        hub_in_top5 += int(any(x in hub_ids and x != p["fact_id"] for x in ids[:5]))
    n = len(probes)
    return {
        "n": n,
        **{f"recall@{k}": hits[k] / n for k in KS},
        "hub_fact_above_target": hub_above / n,
        "other_hub_fact_in_top5": hub_in_top5 / n,
        "missed_rank": sorted(r if r is not None else -1 for r in ranks if r != 0),
        "entity_facts_added_mean": statistics.mean(added) if added else 0.0,
        "probe_ms_p50": statistics.median(probe_ms),
        "statements_per_probe": statistics.mean(stmts),
    }


def run_hub(
    client: GraphClient,
    embedder: Embedder,
    seed: int = SEED,
    arms: tuple[str, ...] = tuple(ARMS),
    keep_graph: bool = False,
) -> dict[str, Any]:
    for a in arms:
        if a not in ARMS:
            raise ValueError(f"unknown arm {a!r}; known: {sorted(ARMS)}")
    tenant = f"l5hub_{uuid.uuid4().hex[:8]}"
    graph = graph_name(tenant)
    rng = random.Random(seed)
    now = int(time.time() * 1000)
    t0 = time.time()
    try:
        apply_schema(client, graph)
        recorder = _Recording(client)
        eng = Engram(recorder, graph, embedder)  # type: ignore[arg-type]
        scope_id = eng.create_scope("project", "hub", now=now - 20_000)
        world = build_world(eng, scope_id, rng, now)
        probes = [{**p, "scope_id": scope_id} for p in world["probes"]]
        t_build = time.time()
        results: dict[str, Any] = {}
        with virtual_now(now):
            ents = eng._resolve_entities(probes[0]["query"], scope_id, now, ["active"])
            hub_fan = next((e["fan"] for e in ents.values() if e["name"] == HUB_NAME), None)
            for name in arms:
                settings, sep = ARMS[name]
                results[name] = _measure(eng, probes, world["hub_fact_ids"], settings, sep, recorder)
        fans = world["predicate_fan"]
        return {
            "config": {
                "seed": seed,
                "hub": HUB_NAME,
                "hub_facts": HUB_FACTS,
                "others": N_OTHERS,
                "facts_per_other": FACTS_PER_OTHER,
                "embedder": type(embedder).__name__,
                "arms": list(arms),
                "settings": {
                    a: {
                        "s_max": s.s_max,
                        "cue_s": s.cue_s,
                        "w_entity": s.w_entity,
                        "w_predicate": s.w_predicate,
                        "separation": sp,
                    }
                    for a, (s, sp) in ARMS.items()
                    if a in arms
                },  # fmt: skip
            },
            "world": {
                "hub_fan_resolved": hub_fan,
                "predicate_fan_mean": statistics.mean(fans.values()),
                "predicate_fan_max": max(fans.values()),
                "facts": HUB_FACTS + N_OTHERS * FACTS_PER_OTHER,
            },
            "arms": results,
            "seconds": {"build": round(t_build - t0, 1), "total": round(time.time() - t0, 1)},
        }
    finally:
        if not keep_graph:
            client.delete_graph(graph)


def hub_criteria(res: dict[str, Any]) -> list[dict[str, Any]]:
    """The pre-registered decision rules (docs/BASELINE.md, "Predicate cue pre-registration", part 2)."""
    a = res["arms"]
    out: list[dict[str, Any]] = []
    tol = 1e-9
    if "sep" in a:
        s1 = a["sep"]["recall@1"]
        out.append(
            {
                "id": "hub: sep recall@1 >= 0.90 (plan §5.3)",
                "hard": False,
                "ok": s1 >= 0.90 - tol,
                "value": [s1],
            }
        )
        out.append(
            {
                "id": "hub: sep recall@1 >= 0.80 (falsification floor)",
                "hard": True,
                "ok": s1 >= 0.80 - tol,
                "value": [s1],
            }
        )
        hb = a["sep"]["hub_fact_above_target"]
        out.append(
            {
                "id": "hub: sep other hub fact above the target <= 10%",
                "hard": False,
                "ok": hb <= 0.10 + tol,
                "value": [hb],
            }
        )
    return out


def render_hub(res: dict[str, Any]) -> str:
    c, w = res["config"], res["world"]
    L = [
        "# L5b hub variant (plan §5.3): one entity, 200 facts of distinct predicates",
        "",
        f"Seed {c['seed']}, embedder {c['embedder']}, hub `{c['hub']}` with {c['hub_facts']} facts (resolved fan "
        f"{w['hub_fan_resolved']}), {c['others']} ordinary entities x {c['facts_per_other']} facts, {w['facts']} facts; "
        f"predicate fan mean {w['predicate_fan_mean']:.2f} (max {w['predicate_fan_max']}). LLM calls: 0.",
        "",
        "| Arm | recall@1 | recall@5 | other hub fact above target | other hub fact in top 5 | entity facts added (mean) | probe ms p50 | statements / probe |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, m in res["arms"].items():
        L.append(
            f"| {name} | {m['recall@1'] * 100:.1f}% | {m['recall@5'] * 100:.1f}% | {m['hub_fact_above_target'] * 100:.1f}% | "
            f"{m['other_hub_fact_in_top5'] * 100:.1f}% | {m['entity_facts_added_mean']:.1f} | {m['probe_ms_p50']:.1f} | "
            f"{m['statements_per_probe']:.1f} |"
        )
    L += ["", "| Criterion | hard | ok | value |", "|---|---|---|---|"]
    for k in res["criteria"]:
        L.append(
            f"| {k['id']} | {'yes' if k['hard'] else 'no'} | {'PASS' if k['ok'] else 'FAIL'} | {k['value']} |"
        )
    L.append("")
    return "\n".join(L)
