"""Family H world: a seeded provenance graph with planted motifs; ground truth in plain Python (no backend).

Shape (one tenant): agents, sources, facts (subject, predicate, status, agent, at), fact->fact and fact->source
derivations, steps (agent, at) that read facts, decisions (agent, at) based on facts, handoffs (from, to) carrying facts.
Every fact has at most one direct source. Ids are zero-padded so lexicographic order is creation order.

Planted on top of the random background (truth counts planted and accidental motifs alike):
* H1a shortcut triangles a->b->c plus a->c, three distinct agents;
* H1b handoff 3-cycles of distinct agents, each handoff carrying a fact derived directly from one common source;
* H2 decisions whose agent read an ancestor of the decision's fact before deciding;
* H3 the 12 path questions (4 plain, 4 traps, 4 unreachable-under-the-constraint), attached to the deep background.
"""

from __future__ import annotations

import random
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from knewat.crucible.l7.common import SEED

SCALES: dict[str, dict[str, int]] = {
    "toy": {"agents": 12, "sources": 20, "facts": 300, "triangles": 5, "cycles": 3},
    "small": {"agents": 50, "sources": 100, "facts": 2000, "triangles": 20, "cycles": 10},
    "medium": {"agents": 100, "sources": 400, "facts": 10000, "triangles": 60, "cycles": 25},
    "large": {"agents": 200, "sources": 1000, "facts": 50000, "triangles": 200, "cycles": 50},
}
PREDICATES = ("owner", "version", "status", "endpoint", "limit")
H3_MAX_HOPS = 8  # bound used by the bounded H3 variants; every planted answer is <= 6 hops
WINDOW = 100  # background attachment window (facts)
LOCAL = 0.6  # share of background parents drawn from the window
ROOTS = (
    0.10  # share of background facts derived from a source only (mean parents per fact 1.35: deep closures)
)


def _id(prefix: str, i: int, width: int) -> str:
    return f"{prefix}{i:0{width}d}"


@dataclass
class HWorld:
    scale: str
    agents: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    facts: list[dict[str, Any]] = field(default_factory=list)  # id, subject, predicate, status, agent, at
    fact_parents: list[tuple[str, str]] = field(default_factory=list)  # (child, parent) fact->fact
    fact_source: list[tuple[str, str]] = field(default_factory=list)  # (fact, source)
    steps: list[dict[str, Any]] = field(default_factory=list)  # id, agent, at, reads
    decisions: list[dict[str, Any]] = field(default_factory=list)  # id, agent, at, based_on
    handoffs: list[dict[str, Any]] = field(default_factory=list)  # id, from, to, at, carries
    h3_pairs: list[dict[str, Any]] = field(default_factory=list)  # id, a, b, kind
    h2_agents: dict[int, list[str]] = field(default_factory=dict)  # N -> agents asked

    def counts(self) -> dict[str, int]:
        return {
            "agents": len(self.agents),
            "sources": len(self.sources),
            "facts": len(self.facts),
            "fact_parents": len(self.fact_parents),
            "fact_source": len(self.fact_source),
            "steps": len(self.steps),
            "reads": sum(len(s["reads"]) for s in self.steps),
            "decisions": len(self.decisions),
            "based_on": sum(len(d["based_on"]) for d in self.decisions),
            "handoffs": len(self.handoffs),
            "carries": sum(len(h["carries"]) for h in self.handoffs),
        }


def h_world(scale: str = "small", seed: int = SEED + 700) -> HWorld:
    """Build the family-H world for ``scale`` (toy / small / medium / large), deterministically from ``seed``."""
    cfg = SCALES[scale]
    rng = random.Random(seed)
    w = HWorld(scale)
    w.agents = [_id("a", i, 3) for i in range(cfg["agents"])]
    w.sources = [_id("s", i, 4) for i in range(cfg["sources"])]
    n = cfg["facts"]
    subjects = [f"subj{i:05d}" for i in range(max(10, n // 10))]
    t = 1_000_000
    parents: dict[str, list[str]] = defaultdict(list)
    src_of: dict[str, str] = {}

    def new_fact(status: str | None = None, agent: str | None = None) -> str:
        nonlocal t
        t += rng.randint(1, 5)
        fid = _id("f", len(w.facts), 6)
        st = status or rng.choices(("active", "superseded", "quarantined"), (75, 15, 10))[0]
        w.facts.append({
            "id": fid, "subject": rng.choice(subjects), "predicate": rng.choice(PREDICATES), "status": st,
            "agent": agent or rng.choice(w.agents), "at": t,
        })  # fmt: skip
        return fid

    def derive(child: str, parent: str) -> None:
        if parent not in parents[child]:
            parents[child].append(parent)
            w.fact_parents.append((child, parent))

    def cite(f: str, s: str) -> None:
        if f not in src_of:
            src_of[f] = s
            w.fact_source.append((f, s))

    # background: 10% roots (source only); else 1 or 2 (50/50) earlier facts, each drawn from the WINDOW most
    # recent facts with probability LOCAL (deep chains with diamonds, as work on one topic builds up) or uniformly
    # from all earlier facts; plus a direct source 30% of the time
    for i in range(n):
        f = new_fact()
        if i < 20 or rng.random() < ROOTS:
            cite(f, rng.choice(w.sources))
            continue
        for _ in range(1 if rng.random() < 0.5 else 2):
            j = rng.randrange(max(0, i - WINDOW), i) if rng.random() < LOCAL else rng.randrange(0, i)
            derive(f, w.facts[j]["id"])
        if rng.random() < 0.30:
            cite(f, rng.choice(w.sources))

    agent_of = {f["id"]: f["agent"] for f in w.facts}

    def set_agent(fid: str, agent: str) -> None:
        agent_of[fid] = agent
        w.facts[int(fid[1:])]["agent"] = agent

    # H1a: planted shortcut triangles (c < b < a in creation order, three distinct agents)
    for _ in range(cfg["triangles"]):
        c_i = rng.randrange(0, n // 2)
        b_i = rng.randrange(c_i + 1, n - 1)
        a_i = rng.randrange(b_i + 1, n)
        a, b, c = (w.facts[k]["id"] for k in (a_i, b_i, c_i))
        derive(a, b)
        derive(b, c)
        derive(a, c)
        x, y, z = rng.sample(w.agents, 3)
        set_agent(a, x)
        set_agent(b, y)
        set_agent(c, z)

    # steps: each reads 1-4 facts created before it
    ho = 0
    for k in range(int(n * 0.6)):
        i = rng.randrange(1, n)
        at = w.facts[i]["at"] + rng.randint(1, 3)
        reads = sorted({w.facts[rng.randrange(0, i)]["id"] for _ in range(rng.randint(1, 4))})
        w.steps.append({"id": _id("st", k, 6), "agent": rng.choice(w.agents), "at": at, "reads": reads})
    # decisions: based on 1-3 facts existing at that time
    for k in range(int(n * 0.05)):
        i = rng.randrange(1, n)
        at = w.facts[i]["at"] + rng.randint(1, 3)
        based = sorted({w.facts[rng.randrange(0, i + 1)]["id"] for _ in range(rng.randint(1, 3))})
        w.decisions.append({"id": _id("d", k, 5), "agent": rng.choice(w.agents), "at": at, "based_on": based})
    # H2 plants: for a fifth of the decisions, the deciding agent read an ancestor (0-4 hops) of a based-on fact before
    planted_deciders: set[str] = set()
    for d in rng.sample(w.decisions, max(1, len(w.decisions) // 5)):
        planted_deciders.add(d["agent"])
        g = d["based_on"][0]
        node, hops = g, rng.randint(0, 4)
        for _ in range(hops):
            if not parents[node]:
                break
            node = rng.choice(parents[node])
        w.steps.append(
            {"id": _id("st", len(w.steps), 6), "agent": d["agent"], "at": d["at"] - 1, "reads": [node]}
        )
    # handoffs: from != to, carrying 1-2 facts
    for _ in range(int(n * 0.03)):
        x, y = rng.sample(w.agents, 2)
        carries = sorted({w.facts[rng.randrange(0, n)]["id"] for _ in range(rng.randint(1, 2))})
        w.handoffs.append({"id": _id("h", ho, 5), "from": x, "to": y, "at": t + ho, "carries": carries})
        ho += 1
    # H1b: planted directed 3-cycles; each handoff carries a fact derived directly from one common source
    by_src: dict[str, list[str]] = defaultdict(list)
    for f, s in w.fact_source:
        by_src[s].append(f)
    rich = sorted(s for s, fs in by_src.items() if len(fs) >= 3)
    for _ in range(cfg["cycles"]):
        s = rng.choice(rich)
        fs = rng.sample(by_src[s], 3)
        x, y, z = rng.sample(w.agents, 3)
        for (u, v), f in zip(((x, y), (y, z), (z, x)), fs, strict=True):
            w.handoffs.append({"id": _id("h", ho, 5), "from": u, "to": v, "at": t + ho, "carries": [f]})
            ho += 1

    # H3: 12 planted pairs hanging off the deep background (a's ancestry is large; b is reachable only via the plant)
    deep = [w.facts[k]["id"] for k in range(int(n * 0.8), n)]
    pairs: list[dict[str, Any]] = []
    for q in range(12):
        kind = ("plain", "trap", "none")[q // 4]
        b = new_fact(status="active")
        for p in rng.sample(deep, 2):
            derive(b, p)
        a = new_fact(status="active")
        for p in rng.sample(deep, 3):
            derive(a, p)
        if kind == "plain":
            chain = [new_fact(status="active") for _ in range(1 + q % 4)]  # path length 2..5
        elif kind == "trap":
            x = new_fact(status=rng.choice(("superseded", "quarantined")))  # the 2-hop shortcut, blocked
            derive(a, x)
            derive(x, b)
            chain = [new_fact(status="active") for _ in range(2 + q % 4)]  # valid path length 3..6
        else:
            chain = [new_fact(status=rng.choice(("superseded", "quarantined"))) for _ in range(1 + q % 3)]
        prev = a
        for c in chain:
            derive(prev, c)
            for p in rng.sample(deep, 1):  # the chain nodes also derive from the background (more to search)
                derive(c, p)
            prev = c
        derive(prev, b)
        pairs.append({"id": f"H3-{q:02d}", "a": a, "b": b, "kind": kind})
    w.h3_pairs = pairs

    # the H2 agents: 8 per N, drawn among the agents of the planted H2 decisions (so most answers are non-empty)
    deciders = sorted(planted_deciders)
    for nh in (0, 2, 4):
        w.h2_agents[nh] = sorted(random.Random(seed + nh).sample(deciders, min(8, len(deciders))))
    return w


# ------------------------------------------------------------------------------------------------ ground truth
class Truth:
    """Every H answer computed from the ledger with plain Python sets and BFS (no backend is consulted)."""

    def __init__(self, w: HWorld):
        self.w = w
        self.par: dict[str, list[str]] = defaultdict(list)
        for c, p in w.fact_parents:
            self.par[c].append(p)
        self.src = dict(w.fact_source)
        self.fact = {f["id"]: f for f in w.facts}

    def closure(self, starts: list[str] | set[str]) -> set[str]:
        """``starts`` plus every fact reachable from them by fact->fact derivations (BFS)."""
        seen = set(starts)
        q = deque(seen)
        while q:
            for p in self.par[q.popleft()]:
                if p not in seen:
                    seen.add(p)
                    q.append(p)
        return seen

    def derives(self, a: str, b: str) -> bool:
        """True if ``a`` derives from ``b`` through >= 1 fact->fact derivation."""
        seen, q = {a}, deque([a])
        while q:
            for p in self.par[q.popleft()]:
                if p == b:
                    return True
                if p not in seen:
                    seen.add(p)
                    q.append(p)
        return False

    @staticmethod
    def _pack(rows: set[tuple[str, ...]]) -> dict[str, Any]:
        s = sorted(rows)
        return {"count": len(s), "first5": [list(r) for r in s[:5]]}

    def h1a(self) -> dict[str, Any]:
        out = set()
        edges = set(self.w.fact_parents)
        ag = {f: d["agent"] for f, d in self.fact.items()}
        for a, b in self.w.fact_parents:
            for c in self.par[b]:
                if (a, c) in edges and len({ag[a], ag[b], ag[c]}) == 3:
                    out.add((a, b, c))
        return self._pack(out)

    def h1b(self) -> dict[str, Any]:
        srcs: dict[str, set[str]] = {
            h["id"]: {self.src[f] for f in h["carries"] if f in self.src} for h in self.w.handoffs
        }
        out_by: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for h in self.w.handoffs:
            out_by[h["from"]].append(h)
        cyc = set()
        for h1 in self.w.handoffs:
            x, y = h1["from"], h1["to"]
            for h2 in out_by[y]:
                z = h2["to"]
                if len({x, y, z}) < 3 or not (x < y and x < z):
                    continue
                for h3 in out_by[z]:
                    if h3["to"] == x and srcs[h1["id"]] & srcs[h2["id"]] & srcs[h3["id"]]:
                        cyc.add((x, y, z))
        return self._pack(cyc)

    def h1c(self) -> dict[str, Any]:
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for f in self.w.facts:
            if f["status"] == "active" and f["id"] in self.src:
                groups[(f["subject"], f["predicate"])].append(f)
        out = set()
        for fs in groups.values():
            for i, f1 in enumerate(fs):
                for f2 in fs[i + 1 :]:
                    a, b = sorted((f1["id"], f2["id"]))
                    if f1["agent"] == f2["agent"] or self.src[a] == self.src[b]:
                        continue
                    if self.derives(a, b) or self.derives(b, a):
                        continue
                    out.add((a, b))
        return self._pack(out)

    def h2(self, agent: str, nh: int) -> dict[str, Any]:
        reads: dict[str, list[int]] = defaultdict(list)  # fact -> times this agent read it
        for s in self.w.steps:
            if s["agent"] == agent:
                for f in s["reads"]:
                    reads[f].append(s["at"])
        out = set()
        for d in self.w.decisions:
            if d["agent"] != agent:
                continue
            frontier, seen = set(d["based_on"]), set(d["based_on"])
            for _ in range(nh):
                frontier = {p for f in frontier for p in self.par[f]} - seen
                seen |= frontier
            for f in seen:
                if any(t < d["at"] for t in reads.get(f, ())):
                    out.add((d["id"], f))
        return self._pack(out)

    def h3(self, a: str, b: str, *, constrained: bool = True, max_hops: int | None = None) -> int | None:
        """Hops of the shortest a->...->b derivation path whose intermediate facts are all active (BFS)."""
        dist, q = {a: 0}, deque([a])
        while q:
            x = q.popleft()
            if x == b:
                return dist[x]
            if x != a and constrained and self.fact[x]["status"] != "active":
                continue
            if max_hops is not None and dist[x] >= max_hops:
                continue
            for p in self.par[x]:
                if p not in dist:
                    dist[p] = dist[x] + 1
                    q.append(p)
        return None

    def h3_valid_path(self, path: list[str], a: str, b: str) -> bool:
        if len(path) < 2 or path[0] != a or path[-1] != b:
            return False
        if any(self.fact[x]["status"] != "active" for x in path[1:-1]):
            return False
        return all(p in self.par[c] for c, p in zip(path, path[1:], strict=False))

    def h4(self) -> list[list[Any]]:
        starts: dict[str, set[str]] = defaultdict(set)
        for d in self.w.decisions:
            starts[d["agent"]].update(d["based_on"])
        per_src: dict[str, set[str]] = defaultdict(set)
        for agent, gs in starts.items():
            for f in self.closure(gs):
                if f in self.src:
                    per_src[self.src[f]].add(agent)
        rows = sorted(((s, len(a)) for s, a in per_src.items()), key=lambda r: (-r[1], r[0]))
        return [list(r) for r in rows[:10]]
