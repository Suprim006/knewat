"""L5b: activation ranking with and without forgetting, on the L2-scale history plus decaying noise (pre-registered in
docs/BASELINE.md).

The history is ``play_scale`` (K sprints) in one tenant of the Plexus arm. For every subject that has a real fact, N noise
facts are added in the same scope; then 90 days of reads are simulated with a seeded schedule (hot set read all the time,
the *critical* facts a Decision rests on read exactly once, 90 days ago, noise read a little at the start and then never).
Probes are fact lookups. Modes: ``off``, ``on`` (activation ranking), ``on+sweep`` (a real sweep first, then ``on``).
No LLM; the clock of the engine is replaced by a virtual ``now`` that is 90 days after the real one.
"""

from __future__ import annotations

import random
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import plexus.engram.service as engram_service
from plexus.activation import Activation, Settings
from plexus.crucible.backends.plexus import PlexusBackend
from plexus.crucible.l2.scale_scenario import play_scale
from plexus.embed import Embedder
from plexus.engram import Engram
from plexus.graph.client import GraphClient
from plexus.graph.tenancy import graph_name

SEED = 20261016
DAY_MS = 86_400_000
NOISE_PREDICATES = (
    "review_note", "todo", "meeting_comment", "tmp_setting", "old_estimate", "retro_item", "ticket_ref", "cleanup_hint",
)  # fmt: skip
NOISE_TEMPLATES = (
    "{pred} mentioned in standup, check again after the release (ticket {n})",
    "someone asked whether {pred} still matches the docs, no answer yet (ticket {n})",
    "{pred} was discussed during the retro, nothing decided (note {n})",
    "revisit the {pred} wording before the next review (item {n})",
    "temporary remark about {pred}, remove when convenient (ref {n})",
    "estimate for changing {pred} was a guess, see thread {n}",
)
KS = (1, 3, 5)
HOT_SHARE = 0.15
NOISE_READ_SHARE = 0.30


@dataclass
class Probe:
    fact_id: str
    query: str
    scope_id: str
    klass: str  # critical | hot | cold


@contextmanager
def virtual_now(t: int) -> Iterator[None]:
    """Make the recall of ``Engram`` see ``t`` as the current time (``Engram.recall`` calls ``_now_ms`` for it)."""
    saved = engram_service._now_ms
    engram_service._now_ms = lambda: t  # type: ignore[assignment]
    try:
        yield
    finally:
        engram_service._now_ms = saved


def add_noise(
    eng: Engram,
    client: GraphClient,
    real: list[dict[str, Any]],
    per_subject: int,
    rng: random.Random,
    window: tuple[int, int],
) -> list[str]:
    """``per_subject`` plausible but unused facts for every (subject, scope) that has a real fact. Returns their ids."""
    seen: dict[tuple[str, str], list[str]] = {}
    for r in real:
        seen.setdefault((r["subject"], r["scope_id"]), []).append(r["predicate"])
    ids: list[str] = []
    counter = 0
    for (subject, scope_id), preds in sorted(seen.items()):
        for i in range(per_subject):
            counter += 1
            base = NOISE_PREDICATES[(counter + i) % len(NOISE_PREDICATES)]
            pred = f"{base}_{counter}"  # unique per fact: no contradiction / supersede between noise facts
            word = rng.choice(preds)
            value = rng.choice(NOISE_TEMPLATES).format(pred=word, n=1000 + counter)
            out = eng.assert_fact(
                subject, pred, value, scope_id, "noise-agent", now=rng.randint(window[0], window[1])
            )
            if out["duplicate_of"] is None:
                ids.append(out["fact_id"])
    return ids


def simulate_reads(
    client: GraphClient,
    graph: str,
    now: int,
    hot: list[str],
    critical: list[str],
    noise: list[str],
    rng: random.Random,
    days: int = 90,
) -> dict[str, int]:
    """Write the seeded 90-day read schedule as READ edges (batches of <= 1000)."""
    reads: list[dict[str, Any]] = []

    def add(fact_id: str, at: int, via: str, step: str, n: int) -> None:
        reads.append({"step_id": step, "n": n, "at": at, "fact_id": fact_id, "via": via})

    for fid in critical:  # read exactly once, 90 days ago
        add(fid, now - days * DAY_MS, "use", f"l5-crit-{fid}", 1)
    for d in range(days, 0, -1):
        at = now - d * DAY_MS + 12 * 3_600_000
        for fid in rng.sample(hot, min(len(hot), rng.randint(3, 8))) if hot else []:
            add(fid, at, "use" if rng.random() < 0.5 else "recall", f"l5-day-{d}", days - d + 1)
    for fid in noise:
        if rng.random() < NOISE_READ_SHARE:
            for _ in range(rng.randint(1, 3)):  # only inside the first 30 days of the window
                d = rng.randint(days - 30, days)
                add(fid, now - d * DAY_MS + 6 * 3_600_000, "recall", f"l5-noise-{d}", days - d + 1)
    for i in range(0, len(reads), 1000):
        client.rw(graph, "crucible/l5_add_reads", {"reads": reads[i : i + 1000], "agent_id": "l5-reader"})
    return {"read_edges": len(reads), "critical_reads": len(critical), "hot_facts": len(hot)}


def _fact_count(client: GraphClient, graph: str) -> int:
    return int(client.graph(graph).ro_query("MATCH (f:Fact) RETURN count(f)").result_set[0][0])


def _measure(
    eng: Engram,
    probes: list[Probe],
    noise: set[str],
    forgetting: bool,
    hits_off: dict[str, bool] | None = None,
) -> dict[str, Any]:
    per_class: dict[str, dict[str, Any]] = {}
    rows_total = noise_rows = chars = 0
    hit5: dict[str, bool] = {}
    for p in probes:
        rows = eng.recall(p.query, p.scope_id, k=max(KS), budget_chars=20_000, forgetting=forgetting)
        ranks = [i for i, r in enumerate(rows) if r["fact_id"] == p.fact_id]
        rank = ranks[0] if ranks else None
        c = per_class.setdefault(p.klass, {"n": 0, **{f"hit@{k}": 0 for k in KS}})
        c["n"] += 1
        for k in KS:
            c[f"hit@{k}"] += int(rank is not None and rank < k)
        hit5[p.fact_id] = rank is not None and rank < max(KS)
        rows_total += len(rows)
        noise_rows += sum(1 for r in rows if r["fact_id"] in noise)
        chars += sum(len(r["text"]) for r in rows)
    overall = {"n": len(probes), **{f"hit@{k}": sum(c[f"hit@{k}"] for c in per_class.values()) for k in KS}}
    out: dict[str, Any] = {
        "recall": {
            name: {"n": c["n"], **{f"recall@{k}": c[f"hit@{k}"] / c["n"] if c["n"] else None for k in KS}}
            for name, c in {**per_class, "all": overall}.items()
        },
        "noise_share": noise_rows / rows_total if rows_total else None,
        "rows_returned": rows_total,
        "chars_per_recall": chars / len(probes) if probes else None,
    }
    if hits_off is not None:
        crit = [p.fact_id for p in probes if p.klass == "critical"]
        out["critical_probe_loss"] = sum(1 for f in crit if hits_off.get(f) and not hit5.get(f))
    out["_hit5"] = hit5
    return out


def run_forgetting(
    client: GraphClient,
    embedder: Embedder,
    k_sprints: int = 20,
    noise_mult: int = 5,
    days: int = 90,
    seed: int = SEED,
    tenant: str | None = None,
    keep_graph: bool = False,
) -> dict[str, Any]:
    tenant = tenant or f"l5f_{uuid.uuid4().hex[:8]}"
    graph = graph_name(tenant)
    t_start = time.time()
    backend = PlexusBackend(tenant, client=client, embedder=embedder)
    try:
        ledger = play_scale(backend, k_sprints)
        real = [dict(r) for r in client.ro(graph, "crucible/l5_real_facts", {"limit": 50_000})]
        t_play = time.time()
        rng = random.Random(seed)
        crit_ids = sorted(r["id"] for r in real if any(not f for f in r["decision_flags"]))
        crit = set(crit_ids)
        others = sorted(r["id"] for r in real if r["id"] not in crit)
        hot_ids = sorted(rng.sample(others, round(HOT_SHARE * len(others)))) if others else []
        hot = set(hot_ids)
        window = (min(r["created_at"] for r in real), max(r["created_at"] for r in real))
        eng = Engram(client, graph, embedder)
        noise_ids = add_noise(eng, client, real, noise_mult, rng, window)
        noise = set(noise_ids)
        t_noise = time.time()
        now = int(time.time() * 1000) + days * DAY_MS
        reads = simulate_reads(client, graph, now, hot_ids, crit_ids, noise_ids, rng, days)
        probes = [
            Probe(
                r["id"],
                f"{r['subject']} {r['predicate']}",
                r["scope_id"],
                "critical" if r["id"] in crit else ("hot" if r["id"] in hot else "cold"),
            )
            for r in real
        ]
        facts_before = _fact_count(client, graph)
        modes: dict[str, Any] = {}
        with virtual_now(now):
            off = _measure(eng, probes, noise, False)
            hits_off = off["_hit5"]
            modes["off"] = off
            modes["on"] = _measure(eng, probes, noise, True, hits_off)
            act = Activation(client, graph, Settings(), clock=lambda: now)
            moved: set[str] = set()
            overlap = 0
            for scope_id in sorted({p.scope_id for p in probes}):
                dry = act.sweep(scope_id, dry_run=True, now=now)
                overlap += sum(1 for c in dry["candidates"] if c["fact_id"] in crit)
                for _ in range(200):  # a sweep moves at most 200 facts per call
                    step = act.sweep(scope_id, dry_run=False, now=now)
                    moved |= set(step["moved"])
                    if not step["moved"]:
                        break
            modes["on+sweep"] = _measure(eng, probes, noise, True, hits_off)
        facts_after = _fact_count(client, graph)
        by_class = {
            "critical": len(moved & crit),
            "hot": len(moved & hot),
            "cold_real": len(moved - crit - hot - noise),
            "noise": len(moved & noise),
        }
        for m in modes.values():
            m.pop("_hit5", None)
        return {
            "config": {
                "sprints": k_sprints,
                "noise_per_subject": noise_mult,
                "days": days,
                "seed": seed,
                "embedder": type(embedder).__name__,
                "ks": list(KS),
            },
            "history": {**ledger.summary(), "real_active_facts": len(real)},
            "classes": {"critical": len(crit), "hot": len(hot), "cold": len(real) - len(crit) - len(hot)},
            "noise_facts": len(noise),
            "reads": reads,
            "modes": modes,
            "sweep": {
                "moved_total": len(moved),
                "moved_by_class": by_class,
                "dry_run_critical_candidates": overlap,
                "fact_nodes_before": facts_before,
                "fact_nodes_after": facts_after,
            },
            "seconds": {"play": round(t_play - t_start, 1), "noise": round(t_noise - t_play, 1)},
        }
    finally:
        if not keep_graph:
            client.delete_graph(graph)
