"""The seeded L8 fault schedule (§4): tokens, 10 change commits, 3 kills, the v2 publication. Identical across arms.

``build_schedule(seed)`` draws everything with ``random.Random(seed)`` once, lands every commit on a scratch copy of
the repository and checks each against the ``ast`` ground truth (the build fails on a mismatch, as L5a's does), and
returns a JSON-able dict (``schedule.json``) plus the sentinel table (``sentinels.json``).
"""

from __future__ import annotations

import random
import shutil
import tempfile
from pathlib import Path
from typing import Any

from knewat.crucible.l8.repo import FUNCS, INVALIDATING, MODULES, Edit, init_repo, initial_modules, key, land
from knewat.crucible.l8.scenario import TASK_BY_ID, nominal_order

SEEDS = tuple(20261016 + r for r in range(1, 6))  # 20261017..20261021
COMMIT_TURNS = range(4, 19)  # 4..18 inclusive
KINDS10 = (
    "value",
    "sibling",
    "docstring",
    "add",
    "module-comment",
    "whitespace",
    "reorder",
    "delete",
    "value",
    "value",
)
BIAS = 0.7
V2_TURN = 12
K1_FROM = 6  # builder, first task turn at/after this with >= 1 call on the task
K2_RANGE = (10, 16)  # researcher during t14 or t16, at/after a seeded turn
K3_RANGE = (8, 20)  # planner, at/after a seeded turn
X3_FUNC = "auth.token_ttl"


def _tokens(rng: random.Random, n: int) -> list[str]:
    nums = rng.sample(range(10000, 100000), n)
    return [f"AX-{x:05d}" for x in nums]


def build_schedule(seed: int, check_dir: Path | None = None) -> dict[str, Any]:
    rng = random.Random(seed)
    pool = iter(_tokens(rng, 200))
    initial = {key(m, f): next(pool) for m, f in FUNCS}
    x2_old = f"AX-3{rng.randrange(10000):04d}"
    while x2_old in initial.values():
        x2_old = f"AX-3{rng.randrange(10000):04d}"
    order = nominal_order(V2_TURN)
    task_turn = {name: t for t, name in order if name in TASK_BY_ID}

    def pending_needs(turn: int, alive: set[str]) -> list[str]:
        return sorted({n for tid, t in task_turn.items() if t >= turn for n in TASK_BY_ID[tid].needs} & alive)

    turns = sorted(rng.sample(list(COMMIT_TURNS), len(KINDS10)))
    kinds = list(KINDS10)
    rng.shuffle(kinds)
    alive = set(initial)
    current = dict(initial)
    history: dict[str, list[dict[str, Any]]] = {k: [{"token": v, "from_turn": 0}] for k, v in initial.items()}
    history["ratelimit.window"].insert(
        0, {"token": x2_old, "from_turn": -1, "note": "S03 note (old sprint document)"}
    )
    edits: list[Edit] = []
    mods = initial_modules(initial)
    trailing: set[str] = set()
    t04_turn = task_turn["t04-survey-infra-security"]
    x3_done = False
    for k, (turn, kind) in enumerate(zip(turns, kinds, strict=True), start=1):
        biased = rng.random() < BIAS
        pend = pending_needs(turn, alive) if biased else []
        cand = pend or sorted(alive)
        e = Edit(k=k, turn=turn, kind=kind, biased=bool(pend))
        if kind == "value":
            n = min(rng.randint(1, 3), len(cand))
            picks = rng.sample(cand, n)
            if not x3_done and turn > t04_turn and X3_FUNC in alive:
                if X3_FUNC not in picks:
                    picks[0] = X3_FUNC
                e.forced = "X3: auth.token_ttl in the first value commit after t04's nominal turn"
                x3_done = True
            e.funcs = sorted(set(picks))
            e.module = e.funcs[0].split(".")[0]
            e.new_tokens = {f: next(pool) for f in e.funcs}
        elif kind == "sibling":
            mods_ok = sorted(
                {
                    c.split(".")[0]
                    for c in cand
                    if sum(1 for a in alive if a.startswith(c.split(".")[0] + ".")) >= 2
                }
            )
            m = rng.choice(mods_ok)
            in_mod = [a for a in sorted(alive) if a.startswith(m + ".")]
            pref = [c for c in cand if c.startswith(m + ".")]
            picks = (
                pref[:1] + rng.sample([x for x in in_mod if x not in pref[:1]], 1)
                if pref
                else rng.sample(in_mod, 2)
            )
            e.funcs, e.module = sorted(picks), m
            e.new_tokens = {f: next(pool) for f in e.funcs}
        elif kind == "docstring":
            f = rng.choice(cand)
            e.funcs, e.module = [f], f.split(".")[0]
        elif kind == "delete":
            f = rng.choice([c for c in cand if c != X3_FUNC] or cand)
            e.funcs, e.module = [f], f.split(".")[0]
        elif kind == "add":
            e.module = rng.choice(sorted(MODULES))
            e.extra = {"name": f"extra_{k}", "token": next(pool)}
        elif kind == "module-comment":
            e.module = rng.choice(sorted(MODULES))
        elif kind == "whitespace":
            f = rng.choice([a for a in sorted(alive) if a not in trailing])
            trailing.add(f)
            e.module, e.extra = f.split(".")[0], {"fn": f.split(".")[1]}
        elif kind == "reorder":
            e.module = rng.choice(sorted(MODULES))
            n = len(mods[e.module].funcs)
            a, b = rng.sample(range(n), 2)
            e.extra = {"a": a, "b": b}
        from knewat.crucible.l8.repo import apply_edit

        apply_edit(mods, e)
        for f, tok in e.new_tokens.items():
            history[f].append({"token": tok, "from_turn": turn, "change": k})
            current[f] = tok
        if kind == "delete":
            alive.discard(e.funcs[0])
            history[e.funcs[0]].append({"token": None, "from_turn": turn, "change": k})
        edits.append(e)
    if not x3_done:
        raise AssertionError(f"seed {seed}: no value commit after t04's nominal turn; X3 cannot be scheduled")
    sched = {
        "seed": seed,
        "initial_tokens": initial,
        "x2_old_token": x2_old,
        "commits": [e.to_json() for e in edits],
        "v2_turn": V2_TURN,
        "kills": {
            "K1": {"agent": "builder", "from_turn": K1_FROM, "after": "first tool call after the claim"},
            "K2": {"agent": "researcher", "from_turn": rng.randint(*K2_RANGE), "tasks": ["t14-ratelimit-spec", "t16-release-notes"],
                   "after": "first Write of an artifact file"},
            "K3": {"agent": "planner", "from_turn": rng.randint(*K3_RANGE), "after": "first memory write (MCP write or Write)"},
        },
        "nominal_order": order,
        "invalidated": sorted({f for e in edits if e.kind in INVALIDATING for f in e.funcs}),
    }  # fmt: skip
    sentinels = {"seed": seed, "functions": history, "final": current, "alive_at_end": sorted(alive)}
    _check(sched, check_dir)
    return {"schedule": sched, "sentinels": sentinels}


def _check(sched: dict[str, Any], check_dir: Path | None) -> None:
    """Land every commit on a scratch repo; ``land`` asserts each against the ast ground truth."""
    tmp = Path(tempfile.mkdtemp(prefix="l8-sched-", dir=check_dir))
    try:
        mods = initial_modules(sched["initial_tokens"])
        init_repo(tmp / "repo", mods)
        mods = initial_modules(sched["initial_tokens"])
        for c in sched["commits"]:
            land(tmp / "repo", mods, Edit.from_json(c))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def all_tokens(sentinels: dict[str, Any], sched: dict[str, Any]) -> set[str]:
    out = {h["token"] for hs in sentinels["functions"].values() for h in hs if h["token"]}
    out |= {c["extra"]["token"] for c in sched["commits"] if c["kind"] == "add"}
    return out
