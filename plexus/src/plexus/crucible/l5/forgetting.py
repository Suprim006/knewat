"""L5b: activation ranking with and without forgetting, on the L2-scale history plus decaying noise (pre-registered in
docs/BASELINE.md).

The history is ``play_scale`` (K sprints) in one tenant of the Plexus arm. For every subject that has a real fact, N noise
facts are added in the same scope; then 90 days of reads are simulated with a seeded schedule (hot set read all the time,
the *critical* facts a Decision rests on read exactly once, 90 days ago, noise read a little at the start and then never).
Probes are fact lookups. Modes: ``off``, ``on`` (activation ranking), ``on+sweep`` (a real sweep first, then ``on``).
No LLM; the clock of the engine is replaced by a virtual ``now`` that is 90 days after the real one.
"""

from __future__ import annotations

import dataclasses
import os
import random
import sqlite3
import statistics
import tempfile
import time
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import plexus.engram.service as engram_service
from plexus.activation import Activation, Settings
from plexus.crucible.backends.plexus import PlexusBackend
from plexus.crucible.l2.scale_scenario import play_scale
from plexus.crucible.l5 import sql_arm
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
BURST_READS = 90
BURST_DAY = 45
# mode -> (settings, forgetting, separation)
MODE_TABLE: dict[str, tuple[Settings, bool, bool | None]] = {
    "off": (Settings(), False, False),
    "on": (Settings(), True, None),
    "on+sweep": (Settings(), True, None),
    "on-mult": (Settings(act_mode="mult", kw_bypass="value"), True, False),
    "kw-fix": (Settings(act_mode="mult", kw_bypass="fact"), True, False),
    "sep": (Settings(act_mode="mult"), False, True),  # the context term as shipped (entity + predicate cues)
    "sep-entity": (
        Settings(act_mode="mult", cues="entity"),
        False,
        True,
    ),  # P1 as first shipped: entity cue only
    "sep+add": (Settings(act_mode="add"), True, True),
    "sep+mult": (
        Settings(act_mode="mult"),
        True,
        True,
    ),  # the shipped default after D-013 (mult + separation)
}


def resolve_mode(name: str) -> tuple[Settings, bool, bool | None]:
    """A mode name, optionally with setting overrides for post-hoc sensitivity runs: ``sep+add[beta=0.01;delta=0]`` (semicolon-separated, the CLI splits modes on commas).

    The bracket form is for exploratory runs only (``demo_data/crucible/l5_posthoc``); the pre-registered modes are
    the bare names of ``MODE_TABLE``.
    """
    base, _, over = name.partition("[")
    if base not in MODE_TABLE:
        raise ValueError(f"unknown mode {name!r}; known: {sorted(MODE_TABLE)}")
    settings, fg, sep = MODE_TABLE[base]
    if over:
        kv = dict(item.split("=", 1) for item in over.rstrip("]").split(";") if item)
        settings = dataclasses.replace(
            settings, **{k: (float(v) if k not in ("act_mode", "kw_bypass") else v) for k, v in kv.items()}
        )
    return settings, fg, sep


@dataclass
class Probe:
    fact_id: str
    query: str
    scope_id: str
    klass: str  # critical | hot | cold
    subject: str = ""


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
    burst: bool = False,
) -> dict[str, int]:
    """Write the seeded 90-day read schedule as READ edges (batches of <= 1000)."""
    reads: list[dict[str, Any]] = []

    def add(fact_id: str, at: int, via: str, step: str, n: int) -> None:
        reads.append({"step_id": step, "n": n, "at": at, "fact_id": fact_id, "via": via})

    for fid in critical:  # read exactly once, 90 days ago
        add(fid, now - days * DAY_MS, "use", f"l5-crit-{fid}", 1)
    if burst:  # every hot fact: BURST_READS reads inside one hour, BURST_DAY days ago
        for fid in hot:
            for i in range(BURST_READS):
                at = now - BURST_DAY * DAY_MS + 12 * 3_600_000 + i * 40_000
                add(fid, at, "use" if rng.random() < 0.5 else "recall", f"l5-burst-{i}", days - BURST_DAY + 1)
    else:
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


def harness_lexical_weight() -> float:
    """The lexical weight (P12 ``fuse_scores``) the L5b / hub harness runs ``Engram.recall`` with.

    Default ``0.0``: the pre-registered D-013 / SQL-arm comparison mirrors the cosine relevance. The recall-check
    (BASELINE.md) sets ``PLEXUS_L5_LEXICAL_WEIGHT`` to ``0.5`` to measure the shipped fusion; the value used is
    written into the results' ``config``. Not read by the product.
    """
    raw = os.environ.get("PLEXUS_L5_LEXICAL_WEIGHT", "").strip()
    if not raw:
        return 0.0
    w = float(raw)
    if not 0.0 <= w <= 1.0:
        raise ValueError(f"PLEXUS_L5_LEXICAL_WEIGHT must be within 0..1, got {raw}")
    return w


class _Recording:
    """Forwards to a ``GraphClient``; counts ``ro`` statements and sums their server ``run_time_ms`` (reset per probe)."""

    def __init__(self, client: GraphClient):
        self._client = client
        self.statements = 0
        self.server_ms = 0.0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def reset(self) -> None:
        self.statements, self.server_ms = 0, 0.0

    def ro(self, *args: Any, **kwargs: Any) -> Any:
        rows = self._client.ro(*args, **kwargs)
        self.statements += 1
        self.server_ms += float(rows.run_time_ms or 0.0)
        return rows


def _fact_count(client: GraphClient, graph: str) -> int:
    return int(client.graph(graph).ro_query("MATCH (f:Fact) RETURN count(f)").result_set[0][0])


def _quantiles(xs: list[float]) -> dict[str, Any]:
    """Deterministic p10..p90 by nearest-rank on the sorted values."""
    ys = sorted(xs)
    out: dict[str, Any] = {"n": len(ys)}
    for name, q in (("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90)):
        out[name] = ys[min(len(ys) - 1, int(q * len(ys)))] if ys else None
    return out


def _measure(
    eng: Engram | sql_arm.SqlRecall,
    probes: list[Probe],
    noise: set[str],
    forgetting: bool,
    hits_off: dict[str, bool] | None = None,
    klass_of: dict[str, str] | None = None,
    settings: Settings | None = None,
    separation: bool | None = None,
    now: int | None = None,
    recorder: _Recording | None = None,
) -> dict[str, Any]:
    """One mode over every probe. ``eng`` is the Plexus ``Engram`` (its client wrapped in ``recorder`` for the
    statement / server-time columns) or the SQL arm (``sql_arm.SqlRecall``, which counts its own statements)."""
    per_class: dict[str, dict[str, Any]] = {}
    rows_total = noise_rows = chars = 0
    hit5: dict[str, bool] = {}
    rank_of: dict[str, int | None] = {}
    top5_of: dict[str, list[str]] = {}
    probe_ms: list[float] = []
    server_ms: list[float] = []
    stmts: list[int] = []
    is_sql = isinstance(eng, sql_arm.SqlRecall)
    above: dict[
        str, int
    ] = {}  # post-hoc diagnostic: class of the rows ranked above the target (all, on a miss)
    klass_of = klass_of or {}
    same_entity = other_entity = cold_n = cold_hot_above = 0
    gaps: list[float] = []
    for p in probes:
        if is_sql:
            eng.reset()
        elif recorder is not None:
            recorder.reset()
        t0 = time.perf_counter()
        kwargs: dict[str, Any] = {"now": now} if is_sql else {}
        rows = eng.recall(
            p.query,
            p.scope_id,
            k=max(KS),
            budget_chars=20_000,
            forgetting=forgetting,
            separation=separation,
            settings=settings,
            **kwargs,
        )
        probe_ms.append((time.perf_counter() - t0) * 1000)
        if is_sql:
            stmts.append(eng.statements)
            server_ms.append(eng.sql_ms)
        elif recorder is not None:
            stmts.append(recorder.statements)
            server_ms.append(recorder.server_ms)
        ranks = [i for i, r in enumerate(rows) if r["fact_id"] == p.fact_id]
        rank = ranks[0] if ranks else None
        rank_of[p.fact_id] = rank
        top5_of[p.fact_id] = [r["fact_id"] for r in rows[: max(KS)]]
        c = per_class.setdefault(p.klass, {"n": 0, **{f"hit@{k}": 0 for k in KS}})
        c["n"] += 1
        for k in KS:
            c[f"hit@{k}"] += int(rank is not None and rank < k)
        hit5[p.fact_id] = rank is not None and rank < max(KS)
        above_rows = rows[: rank if rank is not None else len(rows)]
        if p.klass == "cold":
            cold_n += 1
            cold_hot_above += int(any(klass_of.get(r_["fact_id"]) == "hot" for r_ in above_rows))
        if len(rows) >= 2:
            gaps.append(float(rows[1]["score"]) - float(rows[0]["score"]))
        for r_ in above_rows:
            if r_.get("entity") == p.subject:
                same_entity += 1
            else:
                other_entity += 1
            kind = "noise" if r_["fact_id"] in noise else klass_of.get(r_["fact_id"], "other")
            above[kind] = above.get(kind, 0) + 1
        rows_total += len(rows)
        noise_rows += sum(1 for r in rows if r["fact_id"] in noise)
        chars += sum(len(r["text"]) for r in rows)
    overall = {"n": len(probes), **{f"hit@{k}": sum(c[f"hit@{k}"] for c in per_class.values()) for k in KS}}
    entity_read_ms: float | None = None
    if separation is True and probes:
        t_now = now if now is not None else int(time.time() * 1000)
        times: list[float] = []
        for p in probes[:20]:
            t0 = time.perf_counter()
            eng._resolve_entities(p.query, p.scope_id, t_now, ["active"])
            times.append((time.perf_counter() - t0) * 1000)
        entity_read_ms = float(statistics.median(times))
    out: dict[str, Any] = {
        "recall": {
            name: {"n": c["n"], **{f"recall@{k}": c[f"hit@{k}"] / c["n"] if c["n"] else None for k in KS}}
            for name, c in {**per_class, "all": overall}.items()
        },
        "noise_share": noise_rows / rows_total if rows_total else None,
        "rows_returned": rows_total,
        "ranked_above_target": above,
        "chars_per_recall": chars / len(probes) if probes else None,
        "above_same_entity": same_entity,
        "above_other_entity": other_entity,
        "hot_above_cold": cold_hot_above / cold_n if cold_n else None,
        "hot_above_cold_n": cold_hot_above,
        "gap12": _quantiles(gaps),
        "entity_read_ms": entity_read_ms,
        "probe_ms": _quantiles(probe_ms),
        "server_ms": _quantiles(server_ms)
        if server_ms
        else None,  # Plexus: FalkorDB run_time_ms; SQL: in-process statement time
        "statements_per_probe": statistics.mean(stmts) if stmts else None,
    }
    if hits_off is not None:
        crit = [p.fact_id for p in probes if p.klass == "critical"]
        out["critical_probe_loss"] = sum(1 for f in crit if hits_off.get(f) and not hit5.get(f))
    out["_hit5"] = hit5
    out["_rank"] = rank_of
    out["_top5"] = top5_of
    return out


def _paired(a: dict[str, Any], b: dict[str, Any], probes: list[Probe]) -> dict[str, Any]:
    """Per-probe agreement of two arms' measurements of the same mode (the pre-registered tie test)."""
    ra, rb, ta, tb = a["_rank"], b["_rank"], a["_top5"], b["_top5"]
    only_a1 = [p.fact_id for p in probes if ra.get(p.fact_id) == 0 and rb.get(p.fact_id) != 0]
    only_b1 = [p.fact_id for p in probes if rb.get(p.fact_id) == 0 and ra.get(p.fact_id) != 0]
    only_a5 = [p.fact_id for p in probes if a["_hit5"].get(p.fact_id) and not b["_hit5"].get(p.fact_id)]
    only_b5 = [p.fact_id for p in probes if b["_hit5"].get(p.fact_id) and not a["_hit5"].get(p.fact_id)]
    same_top5 = sum(1 for p in probes if ta.get(p.fact_id) == tb.get(p.fact_id))
    same_top1 = sum(1 for p in probes if (ta.get(p.fact_id) or [None])[0] == (tb.get(p.fact_id) or [None])[0])
    return {
        "n": len(probes),
        "only_plexus_at1": len(only_a1),
        "only_sql_at1": len(only_b1),
        "only_plexus_at5": len(only_a5),
        "only_sql_at5": len(only_b5),
        "same_top1": same_top1,
        "same_top5_list": same_top5,
        "differing_at1": sorted(only_a1 + only_b1),
    }


def run_forgetting(
    client: GraphClient,
    embedder: Embedder,
    k_sprints: int = 20,
    noise_mult: int = 5,
    days: int = 90,
    seed: int = SEED,
    tenant: str | None = None,
    keep_graph: bool = False,
    modes: Sequence[str] = ("off", "on", "on+sweep"),
    burst: bool = False,
    sql: bool = False,
    sql_path: str | None = None,
) -> dict[str, Any]:
    """``sql=True`` (plan §5.4) also exports the graph to SQLite after the reads are written and measures every
    mode with the hand-written-SQL arm (``sql_arm.SqlRecall``) in the same process, paired per probe."""
    for name in modes:
        resolve_mode(name)  # raises on an unknown mode before any work is done
    # off first (control for critical loss); the sweep mutates the graph, so on+sweep goes last
    order = ["off"] + [m for m in dict.fromkeys(modes) if m not in ("off", "on+sweep")]
    if "on+sweep" in modes:
        order.append("on+sweep")
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
        recorder = _Recording(client)
        eng = Engram(recorder, graph, embedder)  # type: ignore[arg-type]
        # P12's lexical fusion is not part of the pre-registered D-013 / SQL-arm comparison (the SQL arm mirrors the
        # cosine relevance); trials-int pins it off here so this harness measures what BASELINE registered.
        # PLEXUS_L5_LEXICAL_WEIGHT overrides the pin for the recall-check ON/OFF comparison (BASELINE "Recall-check").
        eng.lexical_weight = harness_lexical_weight()
        noise_ids = add_noise(eng, client, real, noise_mult, rng, window)
        noise = set(noise_ids)
        t_noise = time.time()
        now = int(time.time() * 1000) + days * DAY_MS
        reads = simulate_reads(client, graph, now, hot_ids, crit_ids, noise_ids, rng, days, burst)
        probes = [
            Probe(
                r["id"],
                f"{r['subject']} {r['predicate']}",
                r["scope_id"],
                "critical" if r["id"] in crit else ("hot" if r["id"] in hot else "cold"),
                r["subject"],
            )
            for r in real
        ]
        facts_before = _fact_count(client, graph)
        modes: dict[str, Any] = {}
        sql_modes: dict[str, Any] = {}
        pairs: dict[str, Any] = {}
        sql_meta: dict[str, Any] = {}
        sqlr: sql_arm.SqlRecall | None = None
        if sql:
            path = sql_path or str(Path(tempfile.mkdtemp(prefix="l5-sql-")) / "l5b.sqlite")
            t_exp = time.perf_counter()
            counts = sql_arm.export_graph(client, graph, path)
            sql_meta = {"path": path, "export_seconds": round(time.perf_counter() - t_exp, 2), "rows": counts,
                        "sql_lines": sql_arm.sql_lines(), "sqlite_version": sqlite3.sqlite_version}  # fmt: skip
            sqlr = sql_arm.SqlRecall(path, embedder)
            graph_acts = Activation(client, graph, Settings(act_mode="mult"), clock=lambda: now).compute(
                [r[0] for r in client.graph(graph).ro_query("MATCH (f:Fact) RETURN f.id").result_set], now
            )
            sql_meta["activation_fidelity"] = sql_arm.activation_fidelity(sqlr, graph_acts, now)
        with virtual_now(now):
            klass_of = {p.fact_id: p.klass for p in probes}
            moved: set[str] = set()
            overlap = 0
            hits_off: dict[str, bool] | None = None
            for name in order:
                if name == "on+sweep":
                    act = Activation(client, graph, Settings(), clock=lambda: now)
                    for scope_id in sorted({p.scope_id for p in probes}):
                        dry = act.sweep(scope_id, dry_run=True, now=now)
                        overlap += sum(1 for c in dry["candidates"] if c["fact_id"] in crit)
                        for _ in range(200):  # a sweep moves at most 200 facts per call
                            step = act.sweep(scope_id, dry_run=False, now=now)
                            moved |= set(step["moved"])
                            if not step["moved"]:
                                break
                settings, fg, sep = resolve_mode(name)
                m = _measure(eng, probes, noise, fg, hits_off, klass_of, settings, sep, now, recorder)
                if name == "off":
                    hits_off = m["_hit5"]
                modes[name] = m
                if sqlr is not None and name != "on+sweep":  # the sweep mutates the graph, not the export
                    ms = _measure(
                        sqlr,
                        probes,
                        noise,
                        fg,
                        hits_off if name != "off" else None,
                        klass_of,
                        settings,
                        sep,
                        now,
                    )
                    sql_modes[name] = ms
                    pairs[name] = _paired(m, ms, probes)
        if sqlr is not None:
            sqlr.close()
        facts_after = _fact_count(client, graph)
        by_class = {
            "critical": len(moved & crit),
            "hot": len(moved & hot),
            "cold_real": len(moved - crit - hot - noise),
            "noise": len(moved & noise),
        }
        for m in (*modes.values(), *sql_modes.values()):
            for key in ("_hit5", "_rank", "_top5"):
                m.pop(key, None)
        return {
            "config": {
                "sprints": k_sprints,
                "noise_per_subject": noise_mult,
                "days": days,
                "seed": seed,
                "embedder": type(embedder).__name__,
                "ks": list(KS),
                "modes": list(order),
                "burst": burst,
                "lexical_weight": eng.lexical_weight,
            },
            "history": {**ledger.summary(), "real_active_facts": len(real)},
            "classes": {"critical": len(crit), "hot": len(hot), "cold": len(real) - len(crit) - len(hot)},
            "noise_facts": len(noise),
            "reads": reads,
            "modes": modes,
            "sql_modes": sql_modes,
            "sql_pairs": pairs,
            "sql_arm": sql_meta,
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
