"""Family G tenant worlds: ``tenant_world(k)`` (seed ``SEED + k``), plain data plus the ground truth computed over it.

Per tenant: 5 agents, 10 sources, 100 facts (99 ordinary + the canary; each derived from 1 source or 1-2 earlier facts,
derived-from depth <= 4), 30 steps reading 1-4 facts, 10 decisions based on 1-3 facts, 5 handoffs carrying 1-2 facts,
10 tasks with dependencies. Ids collide across tenants (``f0001``, ``a1``, ``s01`` exist in every tenant), values carry the
tenant tag (``tenant g0007``), and the canary fact ``canary_<tenant>`` holds a 32-hex secret drawn from the tenant's seed.
"""

from __future__ import annotations

import random
from collections import deque
from typing import Any

from plexus.crucible.l7.common import SEED

T0 = 1_760_000_000_000
OPEN = 9_999_999_999_999
TOPICS = (
    "billing", "search", "auth", "cache", "queue", "storage", "export", "import", "audit", "notifier", "gateway",
    "scheduler", "indexer", "metrics", "tagging", "sharing", "backup", "locking", "sessions", "webhooks",
)  # fmt: skip
NOTES = (
    "requires review", "was approved", "needs a rollback plan", "depends on the vendor", "is rate limited",
    "ships next quarter", "was benchmarked", "has an open risk", "is deprecated", "is owned by platform",
)  # fmt: skip
SCOPE = "sc_global"


def tenant_name(k: int) -> str:
    return f"g{k:04d}"


def tenant_world(k: int) -> dict[str, Any]:
    rng = random.Random(SEED + k)
    ten = tenant_name(k)
    agents = [f"a{i}" for i in range(1, 6)]
    sources = [{"id": f"s{i:02d}", "uri": f"docs/{ten}/s{i:02d}.md"} for i in range(1, 11)]
    secret = f"{rng.getrandbits(128):032x}"
    facts: list[dict[str, Any]] = []
    depth: dict[str, int] = {}
    for i in range(1, 100):
        fid = f"f{i:04d}"
        shallow = [f["id"] for f in facts if depth[f["id"]] <= 3]
        if not shallow or rng.random() < 0.3:
            parents = [rng.choice(sources)["id"]]
            d = 1
        else:
            parents = rng.sample(shallow, k=min(len(shallow), rng.choice((1, 2))))
            d = 1 + max(depth[p] for p in parents)
        topic = rng.choice(TOPICS)
        facts.append({
            "id": fid, "topic": topic, "agent": rng.choice(agents), "parents": parents, "at": T0 + i * 1000,
            "text": f"tenant {ten} {topic} {rng.choice(NOTES)} ref {i}",
        })  # fmt: skip
        depth[fid] = d
    cid = f"canary_{ten}"
    facts.append({
        "id": cid, "topic": "canary", "agent": agents[0], "parents": [sources[0]["id"]], "at": T0 + 100_000,
        "text": f"tenant {ten} canary secret {secret}",
    })  # fmt: skip
    depth[cid] = 1
    ordinary = [f["id"] for f in facts[:-1]]
    steps = []
    n_by_agent: dict[str, int] = {}
    for i in range(1, 31):
        a = rng.choice(agents)
        n_by_agent[a] = n_by_agent.get(a, 0) + 1
        steps.append({
            "id": f"st{i:02d}", "agent": a, "n": n_by_agent[a], "at": T0 + 200_000 + i * 1000,
            "reads": rng.sample(ordinary, k=rng.randint(1, 4)),
        })  # fmt: skip
    tasks = []
    for i in range(1, 11):
        deps = rng.sample([t["id"] for t in tasks], k=min(len(tasks), rng.randint(0, 2)))
        tasks.append({"id": f"tk{i:02d}", "status": "open" if i > 3 else "done", "deps": deps})
    decisions = []
    for i in range(1, 11):
        based = rng.sample(ordinary, k=rng.randint(1, 3))
        if i == 10:
            based = based[:2] + [
                cid
            ]  # the canary has a decision resting on it (impact has something to find)
        decisions.append({
            "id": f"d{i:02d}", "agent": rng.choice(agents), "task": rng.choice(tasks)["id"], "based_on": based,
            "at": T0 + 300_000 + i * 1000, "text": f"tenant {ten} decision {i} {rng.choice(NOTES)}",
        })  # fmt: skip
    handoffs = []
    for i in range(1, 6):
        a, b = rng.sample(agents, 2)
        handoffs.append({
            "id": f"h{i}", "from": a, "to": b, "task": rng.choice(tasks)["id"], "carries": rng.sample(ordinary, k=rng.randint(1, 2)),
            "at": T0 + 400_000 + i * 1000,
        })  # fmt: skip
    return {
        "k": k, "tenant": ten, "secret": secret, "canary": cid, "agents": agents, "sources": sources, "facts": facts,
        "steps": steps, "decisions": decisions, "handoffs": handoffs, "tasks": tasks, "scope": SCOPE,
        "topics": sorted({f["topic"] for f in facts}),
    }  # fmt: skip


def counts(w: dict[str, Any]) -> dict[str, int]:
    """The numbers every loader must reproduce (ledger-derived)."""
    return {
        "agents": len(w["agents"]), "sources": len(w["sources"]), "facts": len(w["facts"]),
        "derived_edges": sum(len(f["parents"]) for f in w["facts"]), "steps": len(w["steps"]),
        "reads": sum(len(s["reads"]) for s in w["steps"]), "decisions": len(w["decisions"]),
        "based_on": sum(len(d["based_on"]) for d in w["decisions"]), "handoffs": len(w["handoffs"]),
        "carries": sum(len(h["carries"]) for h in w["handoffs"]), "tasks": len(w["tasks"]),
        "depends_on": sum(len(t["deps"]) for t in w["tasks"]),
    }  # fmt: skip


# ------------------------------------------------------------------------------------------------ ground truth
def fact_value(w: dict[str, Any], fid: str) -> str:
    return next(f["text"] for f in w["facts"] if f["id"] == fid)


def ancestors(w: dict[str, Any], fid: str, depth: int = 4) -> set[str]:
    """Ids reachable from ``fid`` over DERIVED_FROM in at most ``depth`` hops (facts and sources)."""
    by_id = {f["id"]: f for f in w["facts"]}
    seen: set[str] = set()
    q: deque[tuple[str, int]] = deque([(fid, 0)])
    while q:
        cur, d = q.popleft()
        if d == depth or cur not in by_id:
            continue
        for p in by_id[cur]["parents"]:
            if p not in seen:
                seen.add(p)
                q.append((p, d + 1))
    return seen


def decisions_on(w: dict[str, Any], fid: str) -> set[str]:
    return {d["id"] for d in w["decisions"] if fid in d["based_on"]}


def max_depth(w: dict[str, Any]) -> int:
    by_id = {f["id"]: f for f in w["facts"]}
    memo: dict[str, int] = {}

    def d(fid: str) -> int:
        if fid not in by_id:
            return 0
        if fid not in memo:
            memo[fid] = 1 + max(d(p) for p in by_id[fid]["parents"])
        return memo[fid]

    return max(d(f) for f in by_id)
