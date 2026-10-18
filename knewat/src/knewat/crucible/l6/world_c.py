"""L6-C world: multi-hop recall through ``RELATES`` with ``-ln(fan)`` per hop (BASELINE.md, §5.4 pre-registration, Part 2).

One scope, ``int(4000*scale)`` entities with unique two-word names, ``max(2, int(40*scale))`` hubs, typed ``RELATES``
edges, and 75 questions (25 each at depth 1, 2, 3). The truth is computed in pure Python from the ledger.

**The scoring rule** (``rank_candidates``). From the anchor ``E1`` an entity ``e`` reachable in <= d hops has
``cost(e) = min over walks of sum(ln(fan(v)))`` over the entities ``v`` *entered* along the walk (the anchor is never
entered, ``e`` is), ``fan(v)`` = the number of facts about ``v``. ``hops(e)`` is the hop count of that minimum-cost walk;
when two walks have the same cost (within 1e-9) the one with fewer hops counts. A candidate is a fact with the asked
predicate on an entity with a cost, the anchor excluded. Candidates are ordered by
``(round(cost, 9), hops, entity_id, fact_id)``. ``dist(e)`` is the plain shortest hop distance (what a BFS sees).

**Deviations from the registered text** (each recorded in ``meta`` and in the build report):

* ``fan_range``: an ordinary entity carries ``randint(6, 14)`` facts (mean 10), not exactly 10. With a constant fan every
  target at depth d reached over an all-ordinary walk costs exactly ``d*ln(10)``; at d >= 2 dozens of candidates tie, so
  "redrawn when two candidates tie on cost" can never be satisfied. ``fan_range=(10, 10)`` restores the registered world.
* ``hub_degree``: a hub connects to ``max(5, int(100*scale))`` ordinary entities (about 100 at scale 1.0).
* Question stages. ``S0`` is the registered rule (no entity within hop distance < d, anchor included, has P). Hubs carry
  every predicate and sit within two hops of nearly every anchor, so ``S0`` cannot be met at d = 3. ``S1`` exempts hubs from
  the "closer" test and instead requires the best-by-rule candidate to be at hop distance exactly d; it is only used to top
  up a depth that ``S0`` could not fill, and each question records its ``stage``.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

T0 = 1_700_000_000_000
SEED = 20261016
DEPTHS = (1, 2, 3)
EPS = 1e-9
HUB_FAN = 120

PREDICATES = [
    "color", "owner", "region", "budget", "mentor", "season", "harbor", "ticket", "vendor", "signal",
    "orbit", "ledger", "anchor", "beacon", "cipher", "domain", "engine", "forest", "garden", "helmet",
    "island", "jungle", "kernel", "lantern", "marble", "nectar", "oyster", "planet", "quartz", "rocket",
    "saddle", "timber", "uplink", "valley", "window", "zenith", "bridge", "candle", "dragon", "eagle",
    "falcon", "glacier", "hammer", "iron", "jasper", "kettle", "lemon", "meadow", "needle", "orchard",
    "pepper", "quiver", "ribbon", "silver", "tunnel", "umbrella", "violin", "walnut", "yarrow", "copper",
]  # fmt: skip
KINDS = ["partners", "supplies", "reports", "mentors", "hosts", "funds", "audits", "advises"]
_CONS, _VOW = "bdfgklmnprstvz", "aeiou"


def _words(suffix: str) -> list[str]:
    return sorted(f"{a}{b}{c}{suffix}" for a in _CONS for b in _VOW for c in _CONS)


WORDS_A = random.Random(1).sample(_words("or"), 80)  # two disjoint 80-word lists (80*80 = 6,400 names)
WORDS_B = random.Random(2).sample(_words("el"), 80)


@dataclass
class QuestionC:
    id: str
    depth: int
    anchor_id: str
    anchor_name: str
    predicate: str
    text: str
    answer_fact_id: str
    answer_entity_id: str
    expected_top5: list[str]
    cost_matters: bool
    n_candidates: int
    stage: str = "S0"
    answer_cost: float = 0.0


@dataclass
class WorldC:
    scope_id: str
    entities: list[dict[str, Any]]
    facts: list[dict[str, Any]]
    relates: list[dict[str, Any]]
    questions: list[QuestionC] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        return {
            "entities": len(self.entities), "hubs": sum(1 for e in self.entities if e["hub"]),
            "facts": len(self.facts), "relates": len(self.relates), "questions": len(self.questions),
        }  # fmt: skip

    def adjacency(self) -> dict[str, list[str]]:
        adj: dict[str, set[str]] = {e["id"]: set() for e in self.entities}
        for r in self.relates:
            adj[r["src"]].add(r["dst"])
            adj[r["dst"]].add(r["src"])
        return {k: sorted(v) for k, v in adj.items()}

    def fans(self) -> dict[str, int]:
        out: dict[str, int] = {e["id"]: 0 for e in self.entities}
        for f in self.facts:
            out[f["entity_id"]] += 1
        return out


# ------------------------------------------------------------------------------------------------ the rule
def reach(
    adj: dict[str, list[str]], ln_fan: dict[str, float], anchor: str, depth: int
) -> tuple[dict[str, tuple[float, int]], dict[str, int]]:
    """Layered DP over walks of exactly h hops, h = 1..depth. Returns ``(best, dist)``: ``best[e] = (cost, hops)`` of the
    minimum-cost walk of <= depth hops (fewest hops among equal costs) and ``dist[e]`` the shortest hop distance."""
    cur = {anchor: 0.0}
    best: dict[str, tuple[float, int]] = {}
    dist: dict[str, int] = {anchor: 0}
    for h in range(1, depth + 1):
        nxt: dict[str, float] = {}
        for u, c in cur.items():
            for v in adj[u]:
                if v == anchor:
                    continue
                nc = c + ln_fan[v]
                if v not in nxt or nc < nxt[v]:
                    nxt[v] = nc
        for v, c in nxt.items():
            if v not in best or c < best[v][0] - EPS:
                best[v] = (c, h)
            dist.setdefault(v, h)
        cur = nxt
    return best, dist


def rank_candidates(
    best: dict[str, tuple[float, int]], facts_of: dict[str, dict[str, list[str]]], predicate: str
) -> list[tuple[float, int, str, str]]:
    """Candidates ``(cost, hops, entity_id, fact_id)`` for ``predicate``, in rule order."""
    out = [(c, h, e, fid) for e, (c, h) in best.items() for fid in facts_of.get(e, {}).get(predicate, ())]
    out.sort(key=lambda t: (round(t[0], 9), t[1], t[2], t[3]))
    return out


def truth(world: WorldC, anchor_id: str, predicate: str, depth: int) -> list[str]:
    """The rule's top-5 fact ids for one (anchor, predicate, depth), recomputed from the ledger."""
    adj = world.adjacency()
    ln_fan = {k: math.log(v) for k, v in world.fans().items() if v}
    facts_of: dict[str, dict[str, list[str]]] = {}
    for f in world.facts:
        facts_of.setdefault(f["entity_id"], {}).setdefault(f["predicate"], []).append(f["id"])
    best, _ = reach(adj, ln_fan, anchor_id, depth)
    return [t[3] for t in rank_candidates(best, facts_of, predicate)[:5]]


# ------------------------------------------------------------------------------------------------ the generator
def generate(
    seed: int = SEED,
    scale: float = 1.0,
    *,
    fan_range: tuple[int, int] = (6, 14),
    n_per_depth: int | None = None,
) -> WorldC:
    rng = random.Random(seed)
    n_ent = max(60, int(4000 * scale))
    n_hub = min(max(2, int(40 * scale)), n_ent // 4)
    hub_degree = max(5, int(100 * scale))
    names = rng.sample([(a, b) for a in WORDS_A for b in WORDS_B], n_ent)
    hub_idx = set(rng.sample(range(n_ent), n_hub))
    entities = [
        {"id": f"e{i:05d}", "name": f"{a} {b}", "hub": i in hub_idx} for i, (a, b) in enumerate(names)
    ]
    facts: list[dict[str, Any]] = []
    for e in entities:
        if e["hub"]:
            preds = [PREDICATES[i % len(PREDICATES)] for i in range(HUB_FAN)]
        else:
            preds = rng.sample(PREDICATES, rng.randint(*fan_range))
        for p in preds:
            tok = "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(6))
            facts.append({
                "id": f"f{len(facts):06d}", "entity_id": e["id"], "predicate": p,
                "value": f"{p} of {e['name']} is {tok}",
            })  # fmt: skip
    seen: set[tuple[str, str, str]] = set()
    relates: list[dict[str, Any]] = []

    def link(a: str, b: str) -> None:
        k = rng.choice(KINDS)
        if a != b and (a, b, k) not in seen:
            seen.add((a, b, k))
            relates.append({"src": a, "dst": b, "kind": k})

    ids = [e["id"] for e in entities]
    ordinary = [e["id"] for e in entities if not e["hub"]]
    for e in entities:
        if not e["hub"]:
            for _ in range(rng.randint(2, 5)):
                link(e["id"], rng.choice(ids))
    for e in entities:
        if e["hub"]:
            for o in rng.sample(
                ordinary, min(len(ordinary), rng.randint(int(hub_degree * 0.9), int(hub_degree * 1.1)))
            ):
                a, b = (e["id"], o) if rng.random() < 0.5 else (o, e["id"])
                link(a, b)
    world = WorldC(scope_id="scope_c", entities=entities, facts=facts, relates=relates)
    npd = n_per_depth if n_per_depth is not None else min(25, max(3, round(50 * scale)))
    _questions(world, rng, npd)
    world.meta.update({
        "seed": seed, "scale": scale, "fan_range": list(fan_range), "hub_degree": hub_degree,
        "hub_fan": HUB_FAN, "n_per_depth": npd, "words": [len(WORDS_A), len(WORDS_B)],
    })  # fmt: skip
    return world


def _questions(world: WorldC, rng: random.Random, npd: int) -> None:
    adj = world.adjacency()
    fans = world.fans()
    ln_fan = {k: math.log(v) for k, v in fans.items()}
    hub = {e["id"]: e["hub"] for e in world.entities}
    name = {e["id"]: e["name"] for e in world.entities}
    facts_of: dict[str, dict[str, list[str]]] = {}
    for f in world.facts:
        facts_of.setdefault(f["entity_id"], {}).setdefault(f["predicate"], []).append(f["id"])
    anchors = [e["id"] for e in world.entities if not e["hub"]]
    stats: dict[str, Any] = {"attempts": {}, "stage_counts": {}, "cost_matters_share": {}, "shortfall": {}}
    used: set[str] = set()
    for d in DEPTHS:
        found: list[QuestionC] = []
        attempts = 0
        stage_n = {"S0": 0, "S1": 0}
        for stage in ("S0", "S1"):
            order = anchors[:]
            rng.shuffle(order)
            for a in order:
                if len(found) >= npd:
                    break
                if a in used:
                    continue
                best, dist = reach(adj, ln_fan, a, d)
                closer = [e for e, k in dist.items() if k < d and (stage == "S0" or not hub[e])]
                blocked = set()
                for e in closer:
                    blocked.update(facts_of.get(e, {}))
                pool = PREDICATES[:]
                rng.shuffle(pool)
                for p in pool:
                    attempts += 1
                    if p in blocked or p in facts_of.get(a, {}):
                        continue
                    cands = rank_candidates(best, facts_of, p)
                    if len({c[2] for c in cands if dist[c[2]] == d}) < 2 or len(cands) < 2:
                        continue
                    top = cands[0]
                    if stage == "S1" and dist[top[2]] != d:
                        continue
                    if round(cands[1][0], 9) - round(top[0], 9) <= EPS:  # a cost tie: redrawn
                        continue
                    by_hops = min(cands, key=lambda c: (dist[c[2]], c[2], c[3]))
                    found.append(QuestionC(
                        id=f"C{d}-{len(found) + 1:02d}", depth=d, anchor_id=a, anchor_name=name[a], predicate=p,
                        text=f"{name[a]} {p}", answer_fact_id=top[3], answer_entity_id=top[2],
                        expected_top5=[c[3] for c in cands[:5]], cost_matters=by_hops[2] != top[2],
                        n_candidates=len(cands), stage=stage, answer_cost=round(top[0], 9),
                    ))  # fmt: skip
                    used.add(a)
                    stage_n[stage] += 1
                    break
            if len(found) >= npd:
                break
        world.questions += found
        stats["attempts"][str(d)] = attempts
        stats["stage_counts"][str(d)] = stage_n
        stats["cost_matters_share"][str(d)] = round(
            sum(q.cost_matters for q in found) / max(1, len(found)), 3
        )
        stats["shortfall"][str(d)] = max(0, npd - len(found))
    stats["cost_matters_share"]["all"] = round(
        sum(q.cost_matters for q in world.questions) / max(1, len(world.questions)), 3
    )
    world.meta.update(stats)
