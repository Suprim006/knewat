"""L6 worlds: seeded generators for families A (blast radius with diamonds), B (why-chain depth) and D (cross-sprint
aggregation), plus the truth computed from the generator's own ledger.

A :class:`World` is plain data (lists of dicts) in one backend-independent shape; the loaders in ``stores.py`` put the same
world into SQLite (B1h/B1a), FalkorDB (P arms) and files (B0g/B0r). Ground truth never reads any backend: it is plain
BFS / set arithmetic over this ledger. Sizes follow the pre-registration (BASELINE.md "L6 pre-registration"); ``scale``
shrinks them for the toy tests (``scale=1.0`` is the registered size).
"""

from __future__ import annotations

import random
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

SEED = 20261016
T0 = 1_760_000_000_000
BLAST_SIZES = (10, 100, 1000, 5000)
BLAST_DEPTHS = (2, 4, 8, 12)
CHAIN_DEPTHS = (2, 3, 4, 6, 8, 12)
TOPICS = (
    "billing", "search", "auth", "cache", "queue", "storage", "export", "import", "audit", "notifier", "gateway",
    "scheduler", "indexer", "metrics", "tagging", "sharing", "backup", "locking", "sessions", "webhooks",
    "retention", "quotas", "flags", "routing", "ranking", "sync", "uploads", "previews", "billing-ui", "admin",
    "tenants", "limits", "alerts", "reports", "mailer", "parser", "schema", "migrations", "licenses", "profiles",
)  # fmt: skip
NOTES = (
    "requires review", "was approved", "needs a rollback plan", "depends on the vendor", "is rate limited",
    "ships next quarter", "was benchmarked", "has an open risk", "is deprecated", "is owned by platform",
)  # fmt: skip


@dataclass
class World:
    name: str = ""
    agents: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)  # {id, uri}
    facts: list[dict[str, Any]] = field(
        default_factory=list
    )  # {id, text, topic, agent, at, status, scope, parents}
    steps: list[dict[str, Any]] = field(default_factory=list)  # {id, n, agent, at, reads: [fact ids]}
    decisions: list[dict[str, Any]] = field(default_factory=list)  # {id, text, agent, at, task, based_on}
    handoffs: list[dict[str, Any]] = field(default_factory=list)  # {id, from, to, at, carries}
    supersedes: list[tuple[str, str]] = field(default_factory=list)  # (new fact, old fact)
    tasks: list[dict[str, Any]] = field(default_factory=list)  # {id, status, deps}
    scopes: list[dict[str, Any]] = field(default_factory=list)  # {id, name}
    meta: dict[str, Any] = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        """The numbers every loader must reproduce (node and edge counts)."""
        return {
            "agents": len(self.agents), "sources": len(self.sources), "facts": len(self.facts),
            "derived_edges": sum(len(f["parents"]) for f in self.facts), "steps": len(self.steps),
            "reads": sum(len(s["reads"]) for s in self.steps), "decisions": len(self.decisions),
            "based_on": sum(len(d["based_on"]) for d in self.decisions), "handoffs": len(self.handoffs),
            "carries": sum(len(h["carries"]) for h in self.handoffs), "tasks": len(self.tasks),
            "depends_on": sum(len(t["deps"]) for t in self.tasks), "supersedes": len(self.supersedes),
        }  # fmt: skip

    def fact_index(self) -> dict[str, dict[str, Any]]:
        return {f["id"]: f for f in self.facts}


def _pad(prefix: str, n: int, width: int) -> str:
    return f"{prefix}{n:0{width}d}"


def _fact_text(rng: random.Random, topic: str | None = None) -> tuple[str, str]:
    topic = topic or rng.choice(TOPICS)
    return topic, f"{topic} {rng.choice(NOTES)} (note {rng.randrange(10_000):04d})"


def children_map(world: World) -> dict[str, list[str]]:
    """parent id (source or fact) -> ids of the facts derived from it."""
    ch: dict[str, list[str]] = defaultdict(list)
    for f in world.facts:
        for p in f["parents"]:
            ch[p].append(f["id"])
    return ch


def descendants(ch: dict[str, list[str]], root: str) -> set[str]:
    """Distinct facts reachable from ``root`` over derived-from edges (BFS; plain Python, no database)."""
    seen: set[str] = set()
    q = deque([root])
    while q:
        for nxt in ch.get(q.popleft(), ()):
            if nxt not in seen:
                seen.add(nxt)
                q.append(nxt)
    return seen


# ------------------------------------------------------------------------------------------------ family A
@dataclass
class QuestionA:
    id: str
    index: int
    source: str
    blast: int
    depth: int
    probes: list[str]
    answer: dict[str, Any]

    def text(self) -> str:
        return (
            f"Source {self.source} is poisoned. A fact is affected if it derives from {self.source} directly or through "
            "other facts (at any depth). An agent is affected if it read an affected fact, a decision if it is based on "
            "an affected fact, a handoff if it carries one. Report: facts = the number of affected facts; agents = the "
            "number of distinct affected agents; decisions = the number of affected decisions; handoffs = the number of "
            "affected handoffs; probes = for each of these fact ids, in order, whether it is affected: "
            f"{', '.join(self.probes)}; earliest5 = the ids of the 5 earliest affected facts (smallest `at`), oldest first."
        )

    def fmt(self) -> str:
        return (
            'a JSON object {"facts": int, "agents": int, "decisions": int, "handoffs": int, '
            '"probes": [10 booleans], "earliest5": [5 fact ids]}'
        )


def a_spec(i: int) -> tuple[int, int]:
    b = BLAST_SIZES[i % 4]
    return b, min(BLAST_DEPTHS[(i // 4) % 4], b)


def _levels(total: int, depth: int) -> list[int]:
    base = [max(1, total // depth)] * depth
    base[-1] = max(1, total - sum(base[:-1]))
    return base


def gen_a(scale: float = 1.0, seed: int = SEED, n_questions: int = 24) -> tuple[World, list[QuestionA]]:
    rng = random.Random(seed)
    w = World(name="A")
    w.agents = [_pad("a", i, 3) for i in range(1, 101)]
    w.tasks = [{"id": "t0", "status": "open", "deps": []}]
    raw: list[dict[str, Any]] = []  # facts before id shuffling; keys: key, parents (keys), level, tree
    src_keys: list[str] = []
    trees: dict[str, list[str]] = {}

    def new_source(tag: str) -> str:
        src_keys.append(tag)
        return tag

    def build_tree(source_key: str, total: int, depth: int, tree: str) -> list[str]:
        out: list[str] = []
        prev: list[str] = []
        for lvl, width in enumerate(_levels(total, depth), start=1):
            cur = []
            for _ in range(width):
                key = f"k{len(raw)}"
                if lvl == 1:
                    parents = [source_key]
                else:
                    r = rng.random()
                    k = 1 if r < 0.4 else (2 if r < 0.8 else 3)
                    parents = rng.sample(prev, min(k, len(prev)))
                raw.append({"key": key, "parents": parents, "tree": tree, "level": lvl})
                cur.append(key)
            out += cur
            prev = cur
        return out

    meta: list[dict[str, Any]] = []
    for i in range(n_questions):
        blast, depth = a_spec(i)
        blast = max(1, int(round(blast * scale))) if scale < 1 else blast
        depth = min(depth, blast)
        s = new_source(f"S{i:04d}")
        poisoned = build_tree(s, blast, depth, f"p{i}")
        bg_src = new_source(f"B{i:04d}")
        bg = build_tree(bg_src, max(2, int(0.4 * blast)), min(depth, max(2, int(0.4 * blast))), f"b{i}")
        trees[s] = poisoned
        meta.append(
            {"i": i, "source": s, "blast": blast, "depth": depth, "poisoned": poisoned, "background": bg}
        )
    iso = new_source("SISO")
    for _ in range(max(5, int(100 * scale))):
        raw.append({"key": f"k{len(raw)}", "parents": [iso], "tree": "iso", "level": 1})
    # ids in shuffled order so id order does not reveal creation order; `at` distinct and independent of ids
    order = list(range(len(raw)))
    rng.shuffle(order)
    fid = {raw[j]["key"]: _pad("f", rank + 1, 6) for rank, j in enumerate(order)}
    ats = rng.sample(range(1, 10 * len(raw) + 100), len(raw))
    sid = {k: _pad("s", n + 1, 4) for n, k in enumerate(src_keys)}
    w.sources = [{"id": sid[k], "uri": f"docs/{sid[k]}.md"} for k in src_keys]
    for r, at in zip(raw, ats, strict=True):
        topic, text = _fact_text(rng)
        w.facts.append({
            "id": fid[r["key"]], "text": text, "topic": topic, "agent": rng.choice(w.agents), "at": T0 + at,
            "status": "active", "scope": "global", "tree": r["tree"],
            "parents": [sid.get(p) or fid[p] for p in r["parents"]],
        })  # fmt: skip
    w.facts.sort(key=lambda f: f["id"])
    _add_activity(w, rng, reads=True, dec_rate=0.015, hand_rate=0.01)
    ch = children_map(w)
    fidx = w.fact_index()
    qs: list[QuestionA] = []
    for m in meta:
        s = sid[m["source"]]
        blast_set = descendants(ch, s)
        assert len(blast_set) == m["blast"], (len(blast_set), m["blast"])
        outside = [fid[k] for k in m["background"]]
        inside = sorted(blast_set)
        pos = rng.sample(inside, min(5, len(inside)))
        need = 10 - len(
            pos
        )  # 5 negatives (more only when the blast has fewer than 5 facts, i.e. at toy size)
        neg = rng.sample(outside, min(need, len(outside)))
        if len(neg) < need:
            neg += rng.sample(
                [f["id"] for f in w.facts if f["id"] not in blast_set and f["id"] not in neg], need - len(neg)
            )
        probes = pos + neg
        rng.shuffle(probes)
        qs.append(
            QuestionA(
                f"A{m['i'] + 1:02d}",
                m["i"],
                s,
                m["blast"],
                m["depth"],
                probes,
                truth_a(w, blast_set, probes, fidx),
            )
        )
    w.meta = {"questions": len(qs)}
    return w, qs


def truth_a(w: World, blast: set[str], probes: list[str], fidx: dict[str, dict[str, Any]]) -> dict[str, Any]:
    agents = {s["agent"] for s in w.steps if blast.intersection(s["reads"])}
    decisions = {d["id"] for d in w.decisions if blast.intersection(d["based_on"])}
    handoffs = {h["id"] for h in w.handoffs if blast.intersection(h["carries"])}
    earliest = sorted(blast, key=lambda i: fidx[i]["at"])[:5]
    return {
        "facts": len(blast), "agents": len(agents), "decisions": len(decisions), "handoffs": len(handoffs),
        "probes": [p in blast for p in probes], "earliest5": earliest,
    }  # fmt: skip


def _add_activity(w: World, rng: random.Random, *, reads: bool, dec_rate: float, hand_rate: float) -> None:
    """Steps that READ facts (0-3 reads per fact), decisions and handoffs over random facts of one tree."""
    by_tree: dict[str, list[str]] = defaultdict(list)
    for f in w.facts:
        by_tree[f["tree"]].append(f["id"])
    fat = {f["id"]: f["at"] for f in w.facts}
    if reads:
        events: dict[str, list[tuple[int, str]]] = defaultdict(list)
        readers = {t: rng.sample(w.agents, rng.randint(4, min(len(w.agents), 70))) for t in sorted(by_tree)}
        for f in (
            w.facts
        ):  # each tree is read by its own subset of agents, so "how many agents" varies with the blast
            pool = readers[f["tree"]]
            k = min(len(pool), rng.choices((0, 1, 2, 3), weights=(0.25, 0.35, 0.25, 0.15))[0])
            for a in rng.sample(pool, k):
                events[a].append((f["at"] + rng.randrange(1, 5000), f["id"]))
        n_by_agent: dict[str, int] = defaultdict(int)
        for a in sorted(events):
            ev = sorted(events[a])
            i = 0
            while i < len(ev):
                take = rng.randint(1, 4)
                chunk = ev[i : i + take]
                i += take
                n_by_agent[a] += 1
                w.steps.append({"id": _pad("st", len(w.steps) + 1, 6), "n": n_by_agent[a], "agent": a,
                                "at": max(t for t, _ in chunk), "reads": [fid for _, fid in chunk]})  # fmt: skip
    tree_of = {f["id"]: f["tree"] for f in w.facts}
    trees = sorted(by_tree)
    n_dec = max(1, int(dec_rate * len(w.facts)))
    plan_d = (
        [tree_of[rng.choice(w.facts)["id"]] for _ in range(n_dec)]
        + [t for t in trees if t.startswith("p") for _ in range(2)]
    )  # facts are chosen at random (so decisions follow tree size), and every poisoned tree gets at least 2 decisions
    for t in plan_d:
        pool = by_tree[t]
        based = rng.sample(pool, min(rng.randint(1, 3), len(pool)))
        w.decisions.append({"id": _pad("d", len(w.decisions) + 1, 5), "text": f"Decision on {rng.choice(TOPICS)}",
                            "agent": rng.choice(w.agents), "at": max(fat[b] for b in based) + 10, "task": "t0",
                            "based_on": based})  # fmt: skip
    plan_h = [tree_of[rng.choice(w.facts)["id"]] for _ in range(max(1, int(hand_rate * len(w.facts))))] + [
        t for t in trees if t.startswith("p") for _ in range(2)
    ]
    for t in plan_h:
        pool = by_tree[t]
        a, b = rng.sample(w.agents, 2)
        carries = rng.sample(pool, min(rng.randint(1, 2), len(pool)))
        w.handoffs.append({"id": _pad("h", len(w.handoffs) + 1, 5), "from": a, "to": b,
                           "at": max(fat[c] for c in carries) + 20, "carries": carries})  # fmt: skip


# ------------------------------------------------------------------------------------------------ A-dag
@dataclass
class QuestionDag:
    id: str
    layers: int
    root: str
    probes: list[str]
    answer: dict[str, Any]

    def text(self) -> str:
        return (
            f"Task {self.root} failed. Which tasks are blocked (directly or transitively depend on it)? Report: tasks = "
            "the number of blocked tasks; probes = for each of these task ids, in order, whether it is blocked: "
            f"{', '.join(self.probes)}; first5 = the 5 smallest blocked task ids in string order."
        )


def gen_dag(layers: int, width: int = 6, seed: int = SEED) -> tuple[World, QuestionDag]:
    """BEAT_SQL Probe A: root + ``layers`` layers of ``width`` tasks, each depending on 2 tasks of the layer below.
    The root is the lowest layer's only task: every other task is (transitively) blocked by it.
    """
    rng = random.Random(seed + layers)
    w = World(name=f"dag{layers}")
    w.tasks = [{"id": "root", "status": "open", "deps": []}]
    prev = ["root"]
    for ly in range(1, layers + 1):
        cur = []
        for j in range(width):
            tid = f"t{ly:02d}-{j}"
            deps = rng.sample(prev, min(2, len(prev)))
            w.tasks.append({"id": tid, "status": "open", "deps": deps})
            cur.append(tid)
        prev = cur
    blocked = {t["id"] for t in w.tasks if t["id"] != "root"}
    allt = sorted(blocked)
    free: list[str] = []  # tasks that do not depend on the root (hard negatives for the probes)
    for j in range(20):
        tid = f"u{j:02d}"
        w.tasks.append(
            {"id": tid, "status": "open", "deps": [free[-1]] if free and rng.random() < 0.7 else []}
        )
        free.append(tid)
    probes = rng.sample(allt, 5) + rng.sample(free, 5)
    rng.shuffle(probes)
    ans = {"tasks": len(blocked), "probes": [p in blocked for p in probes], "first5": allt[:5]}
    return w, QuestionDag(f"G{layers:02d}", layers, "root", probes, ans)


# ------------------------------------------------------------------------------------------------ family B
@dataclass
class QuestionB:
    id: str
    chain_index: int
    depth: int
    decision: str
    decision_text: str
    root: str
    answer: dict[str, Any]

    def text(self) -> str:
        return (
            f"Decision {self.decision} (text: '{self.decision_text}') is based on exactly one fact. Following "
            f"derived-from links, that fact reaches source {self.root} through a chain of facts. Report: chain = the "
            f"ordered list of fact ids from the decision's fact down to the fact derived directly from {self.root}; "
            "agent = the agent that asserted that last fact of the chain."
        )

    def fmt(self) -> str:
        return 'a JSON object {"chain": [fact ids in order], "agent": "agent id"}'


def gen_b(scale: float = 1.0, seed: int = SEED) -> tuple[World, list[QuestionB]]:
    rng = random.Random(seed + 1)
    w = World(name="B")
    w.agents = [_pad("a", i, 2) for i in range(1, 31)]
    w.tasks = [{"id": "t0", "status": "open", "deps": []}]
    src_n = 0
    facts: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    n_noise = max(20, int(20_000 * scale))
    at = [T0]

    def tick() -> int:
        at[0] += rng.randint(1, 50)
        return at[0]

    def new_src() -> str:
        nonlocal src_n
        src_n += 1
        sid = _pad("s", src_n, 5)
        sources.append({"id": sid, "uri": f"docs/{sid}.md"})
        return sid

    def new_fact(text: str, topic: str, parents: list[str], tree: str) -> str:
        fid = _pad("f", len(facts) + 1, 6)
        facts.append({"id": fid, "text": text, "topic": topic, "agent": rng.choice(w.agents), "at": tick(),
                      "status": "active", "scope": "global", "tree": tree, "parents": parents})  # fmt: skip
        return fid

    questions: list[QuestionB] = []
    ids_pool: list[tuple[int, int, bool]] = []  # (chain, k, twin)
    chains: list[dict[str, Any]] = []
    for c in range(24):
        depth = CHAIN_DEPTHS[c // 4]
        texts = [_fact_text(rng) for _ in range(depth)]
        dtext = f"Decision to adopt the {rng.choice(TOPICS)} policy v{c}"
        chains.append({"c": c, "depth": depth, "texts": texts, "dtext": dtext})
        ids_pool += [(c, 0, False), (c, 0, True)]
    # build original and twin of every chain; interleave creation so ids do not separate twins
    built: dict[tuple[int, bool], dict[str, Any]] = {}
    for c, _, twin in ids_pool:
        ch = chains[c]
        root = new_src()
        # create from the root side so that f_i can name f_{i+1} as a parent
        fid_chain: list[str] = [""] * ch["depth"]
        for i in range(ch["depth"] - 1, -1, -1):
            parents = [root] if i == ch["depth"] - 1 else [fid_chain[i + 1]]
            for _ in range(3):  # three distractor parents, each a dead end on its own source
                dsrc = new_src()
                dt, dtx = _fact_text(rng)
                parents.append(new_fact(dtx, dt, [dsrc], f"dis{c}{int(twin)}"))
            topic, text = ch["texts"][i]
            fid_chain[i] = new_fact(text, topic, parents, f"chain{c}{int(twin)}")
        did = _pad("d", len(decisions) + 1, 5)
        decisions.append({"id": did, "text": ch["dtext"], "agent": rng.choice(w.agents), "at": tick(), "task": "t0",
                          "based_on": [fid_chain[0]]})  # fmt: skip
        built[(c, twin)] = {"decision": did, "root": root, "chain": fid_chain}
    # background noise: facts derived from 500 sources (depth <= 3)
    nsrc = max(5, int(500 * scale))
    noise_src = [new_src() for _ in range(nsrc)]
    noise_ids: list[str] = []
    for _ in range(n_noise):
        t, tx = _fact_text(rng)
        if noise_ids and rng.random() < 0.4:
            parents = [rng.choice(noise_ids[-200:])]
        else:
            parents = [rng.choice(noise_src)]
        noise_ids.append(new_fact(tx, t, parents, "noise"))
    # a Python-side shuffle of ids would hide creation order; ids here are creation-ordered by design but the decision
    # for the original chain and its twin are created consecutively, so the id alone does not say which is "first"
    w.sources, w.facts, w.decisions = sources, facts, decisions
    fidx = {f["id"]: f for f in facts}
    for c in range(24):
        b = built[(c, False)]
        ans = {"chain": b["chain"], "agent": fidx[b["chain"][-1]]["agent"]}
        # truth check from the ledger: the chain is the unique path decision-fact -> root
        assert _path_to(w, b["chain"][0], b["root"]) == b["chain"]
        questions.append(
            QuestionB(
                f"B{c + 1:02d}", c, chains[c]["depth"], b["decision"], chains[c]["dtext"], b["root"], ans
            )
        )
    w.meta = {"twins": {str(c): built[(c, True)] for c in range(24)}}
    return w, questions


def _path_to(w: World, start: str, root: str) -> list[str]:
    """The unique derived-from path from a fact to a source (DFS over the ledger)."""
    fidx = w.fact_index()
    paths: list[list[str]] = []

    def dfs(node: str, path: list[str]) -> None:
        for p in fidx[node]["parents"]:
            if p == root:
                paths.append(path)
            elif p in fidx:
                dfs(p, [*path, p])

    dfs(start, [start])
    assert len(paths) == 1, len(paths)
    return paths[0]


# ------------------------------------------------------------------------------------------------ family D
D_RANGES = ((1, 200), (1, 100), (101, 200), (41, 160))
D_TEMPLATES = (
    "superseded_decisions",
    "top_forgetter",
    "shared_sources",
    "superseded_handoffs",
    "top_sprints",
    "cross_agent_supersedes",
)
HOT = {
    20: 10,
    60: 9,
    90: 8,
    130: 7,
    170: 6,
    190: 5,
}  # sprint -> forgotten facts, planted so top-3 is unique per range


@dataclass
class QuestionD:
    id: str
    index: int
    template: str
    variant: int
    lo: int
    hi: int
    k: int
    answer: Any

    def text(self) -> str:
        scope = "Across all sprints" if self.variant == 0 else f"Across sprints S{self.lo:03d}-S{self.hi:03d}"
        t = self.template
        if t == "superseded_decisions":
            return f"{scope}: how many decisions are based on at least one fact that was later superseded?"
        if t == "top_forgetter":
            return f"{scope}: which agent asserted the most facts that were later forgotten, and how many?"
        if t == "shared_sources":
            return (
                f"{scope}: which shared sources (ids starting 'shared-') are cited by decisions (through the facts they are "
                f"based on) in MORE than {self.k} different sprints?"
            )
        if t == "superseded_handoffs":
            return f"{scope}: how many handoffs carry at least one fact that was later superseded?"
        if t == "top_sprints":
            return f"{scope}: which 3 sprints have the most later-forgotten facts? List the sprint tags, most first."
        return f"{scope}: for how many facts is the fact that superseded it asserted by a different agent than the original?"

    def fmt(self) -> str:
        return {
            "superseded_decisions": "an integer",
            "top_forgetter": 'a JSON object {"agent": "agent id", "count": int}',
            "shared_sources": "a JSON list of source ids (sorted)",
            "superseded_handoffs": "an integer",
            "top_sprints": 'a JSON list of 3 sprint tags such as "S017", most first',
            "cross_agent_supersedes": "an integer",
        }[self.template]


def _tag(s: int) -> str:
    return f"S{s:03d}"


def gen_d(scale: float = 1.0, seed: int = SEED) -> tuple[World, list[QuestionD]]:
    for attempt in range(200):
        w, qs = _gen_d_once(scale, seed + 100 * attempt)
        if qs is not None:
            w.meta["attempt"] = attempt
            return w, qs
    raise RuntimeError("no unambiguous family D world in 200 draws")


def _gen_d_once(scale: float, seed: int) -> tuple[World, list[QuestionD] | None]:
    rng = random.Random(seed + 3)
    n_sprints = 200 if scale >= 1 else max(8, int(200 * scale))
    hot = HOT if n_sprints == 200 else {max(1, round(k * n_sprints / 200)): v for k, v in HOT.items()}
    w = World(name="D")
    w.agents = [_pad("agent-", i, 2) for i in range(1, 13)]
    w.tasks = [{"id": "t0", "status": "open", "deps": []}]
    shared = [_pad("shared-", i, 2) for i in range(1, 31)]
    w.sources = [{"id": s, "uri": f"docs/shared/{s}.md"} for s in shared]
    weights = [1.0 / (1 + 0.35 * i) for i in range(30)]
    spr_facts: dict[int, list[str]] = {}
    forgot_by: dict[int, list[str]] = {}
    sup_pairs: list[tuple[str, str]] = []
    clock = T0
    for s in range(1, n_sprints + 1):
        tag = _tag(s)
        w.scopes.append({"id": f"scope:{tag}", "name": tag})
        own = [f"src-{tag}-{c}" for c in "abc"]
        w.sources += [{"id": o, "uri": f"docs/{tag}/{o}.md"} for o in own]
        n = 18 + max(0, hot.get(s, 0) - 2)
        ids = []
        for j in range(n):
            clock += rng.randint(5, 40)
            topic, text = _fact_text(rng)
            parent = rng.choice(own) if rng.random() < 0.7 else rng.choices(shared, weights)[0]
            fid = f"f-{tag}-{j + 1:02d}"
            w.facts.append({"id": fid, "text": text, "topic": topic, "agent": rng.choice(w.agents), "at": clock,
                            "status": "active", "scope": f"scope:{tag}", "tree": tag, "parents": [parent]})  # fmt: skip
            ids.append(fid)
        spr_facts[s] = ids
        fidx_s = {f["id"]: f for f in w.facts[-n:]}
        k_forget = hot.get(s, 0) or min(3, sum(rng.random() < 0.06 for _ in range(n)))
        pool = list(ids)
        rng.shuffle(pool)
        forgotten = pool[:k_forget]
        rest = pool[k_forget:]
        for f in forgotten:
            fidx_s[f]["status"] = "forgotten"
        forgot_by[s] = forgotten
        # supersede 3 pairs: old (a non-forgotten fact) is replaced by a later fact of the same sprint (asserted later)
        later = sorted(rest, key=lambda i: fidx_s[i]["at"])
        olds = later[:3] if len(later) >= 6 else []
        news = later[-3:] if len(later) >= 6 else []
        for old, new in zip(olds, news, strict=False):
            fidx_s[old]["status"] = "superseded"
            sup_pairs.append((new, old))
        for _ in range(8):
            clock += 7
            based = rng.sample(ids, rng.randint(1, 3))
            w.decisions.append({"id": f"d-{tag}-{len(w.decisions) + 1:05d}", "text": f"Decision in {tag} on {rng.choice(TOPICS)}",
                                "agent": rng.choice(w.agents), "at": clock, "task": "t0", "based_on": based, "sprint": s})  # fmt: skip
        for _ in range(5):
            clock += 7
            a, b = rng.sample(w.agents, 2)
            w.handoffs.append({"id": f"h-{tag}-{len(w.handoffs) + 1:05d}", "from": a, "to": b, "at": clock,
                               "carries": rng.sample(ids, rng.randint(1, 2)), "sprint": s})  # fmt: skip
    w.supersedes = sup_pairs
    fidx = w.fact_index()
    sprint_of = {f["id"]: int(f["tree"][1:]) for f in w.facts}
    qs: list[QuestionD] = []
    for i in range(24):
        t, v = divmod(i, 4)
        lo, hi = D_RANGES[v]
        if n_sprints != 200:  # toy size: the same four ranges, scaled to the number of sprints
            lo, hi = max(1, round(lo * n_sprints / 200)), min(n_sprints, round(hi * n_sprints / 200))
        ans, k = truth_d(w, fidx, sprint_of, D_TEMPLATES[t], lo, hi)
        if ans is None:
            return w, None
        qs.append(QuestionD(f"D{i + 1:02d}", i, D_TEMPLATES[t], v, lo, hi, k, ans))
    w.meta = {"sprints": n_sprints}
    return w, qs


def truth_d(
    w: World, fidx: dict[str, dict[str, Any]], sprint_of: dict[str, int], template: str, lo: int, hi: int
) -> tuple[Any, int]:
    inr = lambda fid: lo <= sprint_of[fid] <= hi  # noqa: E731
    sup = {f["id"] for f in w.facts if f["status"] == "superseded"}
    if template == "superseded_decisions":
        return sum(1 for d in w.decisions if lo <= d["sprint"] <= hi and sup.intersection(d["based_on"])), 0
    if template == "superseded_handoffs":
        return sum(1 for h in w.handoffs if lo <= h["sprint"] <= hi and sup.intersection(h["carries"])), 0
    if template == "cross_agent_supersedes":
        return sum(1 for new, old in w.supersedes if inr(old) and fidx[new]["agent"] != fidx[old]["agent"]), 0
    forgotten = [f for f in w.facts if f["status"] == "forgotten" and inr(f["id"])]
    if template == "top_forgetter":
        cnt: dict[str, int] = defaultdict(int)
        for f in forgotten:
            cnt[f["agent"]] += 1
        top = sorted(cnt.values(), reverse=True)
        if not top or (len(top) > 1 and top[0] == top[1]):
            return None, 0
        a = max(cnt, key=lambda x: cnt[x])
        return {"agent": a, "count": cnt[a]}, 0
    if template == "top_sprints":
        cnt2: dict[int, int] = defaultdict(int)
        for f in forgotten:
            cnt2[sprint_of[f["id"]]] += 1
        order = sorted(cnt2.items(), key=lambda kv: (-kv[1], kv[0]))
        vals = [c for _, c in order[:4]]
        if len(set(vals[:3])) < 3 or (len(vals) > 3 and vals[3] == vals[2]):
            return None, 0
        return [_tag(s) for s, _ in order[:3]], 0
    # shared_sources
    cited: dict[str, set[int]] = defaultdict(set)
    for d in w.decisions:
        if not lo <= d["sprint"] <= hi:
            continue
        for b in d["based_on"]:
            p = fidx[b]["parents"][0]
            if p.startswith("shared-"):
                cited[p].add(d["sprint"])
    for k in range(0, 200):
        hit = sorted(s for s, sp in cited.items() if len(sp) > k)
        if 3 <= len(hit) <= 12:
            return hit, k
    return None, 0
