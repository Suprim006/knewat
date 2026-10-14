"""Ablation (D-001): what breaks when the graph's relationships are removed?

The Plexus arm is seeded with a small scripted team run, then the relationship types the features rest on are deleted
(``DEPENDS_ON``, ``BASED_ON``, ``DERIVED_FROM``, ``READ``; ``PlexusBackend.ablate`` runs the bounded
``crucible/strip_edges`` query). Capability probes then run on the intact graph and on the stripped one:

* every probe that *needs* one of those edges should pass intact and fail ablated;
* control probes (as-of time travel, recall, contradiction flagging, claim exclusivity) do not use those edges and
  should pass in both, which shows the ablation removes the features it claims to and nothing else.

``P-abl`` additionally re-runs the L1 tests C4 (dependency ordering) and C8 (forget by source) with the edges stripped
as soon as they are written, so the violation counts of the intact and the ablated arm can be compared directly.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Any

from plexus.crucible.api import BackendSpec
from plexus.crucible.backends import register_arm
from plexus.crucible.backends.plexus import PlexusBackend
from plexus.crucible.config import L1Config
from plexus.crucible.harness import ArmRun, Env
from plexus.crucible.l1 import run_test

STRIPPED = ("DEPENDS_ON", "BASED_ON", "DERIVED_FROM", "READ")


class AblatedPlexus(PlexusBackend):
    """Plexus whose dependency / provenance / read edges are deleted right after each write that creates them."""

    def __init__(self, *args: Any, **kw: Any):
        super().__init__(*args, **kw)
        self.name, self.label = "P-abl", "Plexus (edges stripped)"
        self.stripped: dict[str, int] = dict.fromkeys(STRIPPED, 0)

    def _strip(self) -> None:
        for k, v in self.ablate().items():
            self.stripped[k] += v

    def create_tasks(self, tasks: Sequence[dict[str, Any]]) -> list[str]:
        out = super().create_tasks(tasks)
        self._strip()
        return out

    def assert_fact(self, *args: Any, **kw: Any) -> dict[str, Any]:
        out = super().assert_fact(*args, **kw)
        if kw.get("source_id") or kw.get("derived_from"):
            self._strip()
        return out

    def record_decision(self, *args: Any, **kw: Any) -> str:
        out = super().record_decision(*args, **kw)
        self._strip()
        return out


def _register(env: Env) -> None:
    def make(spec: BackendSpec) -> AblatedPlexus:
        return AblatedPlexus(
            spec.tenant, host=spec.host or None, port=spec.port or None, embedder=spec.embedder
        )

    register_arm("P-abl", make)


# -- scripted seed ---------------------------------------------------------------------------------------------------


def seed(b: PlexusBackend) -> dict[str, Any]:
    """A miniature Acme run with known ground truth. Returns the ids the probes need."""
    for a in ("planner", "researcher", "builder"):
        b.register_agent(a, a)
    b.create_tasks(
        [
            {"id": "T1", "title": "research the API"},
            {"id": "T2", "title": "design", "depends_on": ["T1"]},
            {"id": "T3", "title": "build", "depends_on": ["T2"]},
            {"id": "T4", "title": "test", "depends_on": ["T3"]},
            {"id": "T5", "title": "write the README"},
        ]
    )
    src1, src2 = b.add_source("doc://acme-spec"), b.add_source("doc://team-wiki")
    f1 = b.assert_fact("researcher", "Acme API", "version", "v1", source_id=src1)["fact_id"]
    f2 = b.assert_fact("researcher", "Acme API", "database", "Postgres 16", source_id=src1)["fact_id"]
    f3 = b.assert_fact(
        "researcher", "Acme API summary", "digest", "v1 on Postgres 16", derived_from=[f1, f2]
    )["fact_id"]
    f4 = b.assert_fact("planner", "Acme API", "owner", "platform team", source_id=src2)["fact_id"]
    hits = b.recall("builder", "Acme API version", k=5)  # builder READs facts at this step
    time.sleep(0.01)
    step = b.knew_at("builder", 10**6)["step_n"]
    d1 = b.record_decision("builder", "T2", "build against v1 on Postgres 16", [f1, f2])
    b.handoff("researcher", "builder", "T1", "spec is ready", fact_ids=[f1])
    time.sleep(0.01)
    t_mid = int(time.time() * 1000)
    time.sleep(0.01)
    f1b = b.assert_fact("researcher", "Acme API", "version", "v2")["fact_id"]  # supersedes f1
    return {
        "src1": src1, "src2": src2, "f1": f1, "f2": f2, "f3": f3, "f4": f4, "f1b": f1b, "d1": d1,
        "builder_step": step, "t_mid": t_mid, "recalled": [h["fact_id"] for h in hits],
    }  # fmt: skip


Probe = Callable[[PlexusBackend, dict[str, Any]], tuple[bool, str]]


def _dependency_order(b: PlexusBackend, ids: dict[str, Any]) -> tuple[bool, str]:
    claimed = []
    for _ in range(6):
        t = b.claim_next_task("builder", 600_000)
        if t is not None:
            claimed.append(t["id"])
    ok = sorted(claimed) == ["T1", "T5"]
    return ok, f"claimable without completing anything: {sorted(claimed)} (expected ['T1', 'T5'])"


def _blocked(b: PlexusBackend, ids: dict[str, Any]) -> tuple[bool, str]:
    got = sorted(b.blocked_by_failure("T1"))
    return got == ["T2", "T3", "T4"], f"blocked_by_failure(T1) = {got} (expected ['T2', 'T3', 'T4'])"


def _why_decision(b: PlexusBackend, ids: dict[str, Any]) -> tuple[bool, str]:
    r = b.why(ids["d1"])
    got = {f["id"]: f["asserted_by"] for f in r["facts"]}
    ok = set(got) == {ids["f1"], ids["f2"]} and all(v == ["researcher"] for v in got.values())
    return ok, f"why(decision) lists {len(got)} fact(s) with their asserting agents (expected 2)"


def _why_sources(b: PlexusBackend, ids: dict[str, Any]) -> tuple[bool, str]:
    r = b.why(ids["f3"])
    srcs = r["facts"][0]["sources"] if r["facts"] else []
    return ids["src1"] in srcs, f"why(derived fact) reaches source(s) {len(srcs)} (expected the spec source)"


def _knew_at(b: PlexusBackend, ids: dict[str, Any]) -> tuple[bool, str]:
    r = b.knew_at("builder", ids["builder_step"])
    got = {f["fact_id"] for f in r["facts"]}
    return ids["f1"] in got, f"knew_at(builder, step) lists {len(got)} fact(s) read (expected to include v1)"


def _who_knew(b: PlexusBackend, ids: dict[str, Any]) -> tuple[bool, str]:
    r = b.who_knew(ids["f1"])
    return "builder" in r["agents"], f"who_knew(v1) = {r['agents']} (expected ['builder'])"


def _forget(b: PlexusBackend, ids: dict[str, Any]) -> tuple[bool, str]:
    r = b.forget_source(ids["src1"])
    gone = set(r["fact_ids"])
    left = {h["fact_id"] for h in b.recall("builder", "Acme API summary digest v1 on Postgres 16", k=10)}
    ok = {ids["f1"], ids["f2"], ids["f3"]} <= gone and not left & {ids["f1"], ids["f2"], ids["f3"]}
    return (
        ok,
        f"forget_source forgot {len(gone)} fact(s) (expected 3: two from the source + one derived from them)",
    )


def _as_of(b: PlexusBackend, ids: dict[str, Any]) -> tuple[bool, str]:
    r = b.as_of("Acme API", "version", ids["t_mid"])
    return bool(r) and r["value"] == "v1", f"as_of(version, before v2) = {r and r['value']!r} (expected 'v1')"


def _recall(b: PlexusBackend, ids: dict[str, Any]) -> tuple[bool, str]:
    got = {h["fact_id"] for h in b.recall("builder", "Acme API owner platform team", k=5)}
    return ids["f4"] in got, "recall finds the owner fact"


def _contradiction(b: PlexusBackend, ids: dict[str, Any]) -> tuple[bool, str]:
    r = b.assert_fact("builder", "Acme API", "owner", "billing team")
    return r["contradicts"] == [
        ids["f4"]
    ], f"conflicting owner flagged: {len(r['contradicts'])} contradiction(s)"


def _supersession(b: PlexusBackend, ids: dict[str, Any]) -> tuple[bool, str]:
    hist = {h["fact_id"]: h for h in b.facts("Acme API", "version")}
    ok = hist[ids["f1"]]["status"] == "superseded" and hist[ids["f1b"]]["supersedes"] == [ids["f1"]]
    return ok, "v1 is superseded by v2 (SUPERSEDES edge kept)"


def _exclusive_claims(b: PlexusBackend, ids: dict[str, Any]) -> tuple[bool, str]:
    b.create_tasks([{"id": "X1", "title": "x1", "priority": 9}, {"id": "X2", "title": "x2", "priority": 9}])
    a = b.claim_next_task("planner", 600_000)
    c = b.claim_next_task("researcher", 600_000)
    return bool(a and c and a["id"] != c["id"]), "two agents never get the same task"


# (name, what it needs, probe). `needs` empty = control probe.
PROBES: list[tuple[str, str, Probe]] = [
    # controls first: they need none of the stripped edges (and forget_source, which changes what they see, runs last)
    ("as-of time travel (C6)", "", _as_of),
    ("recall", "", _recall),
    ("contradiction flagged at write time (C3)", "", _contradiction),
    ("supersession history", "", _supersession),
    ("exclusive claims (C1)", "", _exclusive_claims),
    ("dependency-aware claims (C4)", "DEPENDS_ON", _dependency_order),
    ("blocked_by_failure", "DEPENDS_ON", _blocked),
    ("why(decision): evidence + who asserted it", "BASED_ON", _why_decision),
    ("why(fact): source lineage", "DERIVED_FROM", _why_sources),
    ("knew_at(agent, step)", "READ", _knew_at),
    ("who_knew(fact)", "READ", _who_knew),
    ("forget by source, cascading (C8)", "DERIVED_FROM", _forget),
]


def _run_probes(env: Env, ablated: bool) -> tuple[dict[str, Any], dict[str, int]]:
    out: dict[str, Any] = {}
    removed: dict[str, int] = {}
    with ArmRun(env, "P") as run:
        b = run.open("abl")
        assert isinstance(b, PlexusBackend)
        ids = seed(b)
        before = b.edge_counts()
        if ablated:
            removed = b.ablate()
        after = b.edge_counts()
        out["_edges_before"] = {k: before.get(k, 0) for k in STRIPPED}
        out["_edges_after"] = {k: after.get(k, 0) for k in STRIPPED}
        for name, needs, fn in PROBES:
            try:
                ok, detail = fn(b, ids)
            except Exception as exc:  # noqa: BLE001 - a probe that crashes is a capability that failed
                ok, detail = False, f"{type(exc).__name__}: {exc}"[:160]
            out[name] = {"needs": needs, "passed": bool(ok), "detail": detail}
    return out, removed


def run_ablation(env: Env, cfg: L1Config, log: Callable[[str], None] = print) -> dict[str, Any]:
    log("  ablation: capability probes on the intact graph")
    intact, _ = _run_probes(env, ablated=False)
    log("  ablation: capability probes after deleting DEPENDS_ON, BASED_ON, DERIVED_FROM, READ")
    stripped, removed = _run_probes(env, ablated=True)
    caps = []
    for name, needs, _ in PROBES:
        caps.append(
            {
                "capability": name,
                "needs": needs or "(none: control)",
                "intact": intact[name],
                "ablated": stripped[name],
                "breaks_without_edges": intact[name]["passed"] and not stripped[name]["passed"],
            }
        )
    _register(env)
    small = L1Config(
        **{**cfg.__dict__, "reps": min(cfg.reps, 3), "tests": ("C4", "C8"), "arms": ("P", "P-abl")}
    )
    l1: dict[str, Any] = {}
    for arm in ("P", "P-abl"):
        l1[arm] = {}
        for test in ("C4", "C8"):
            r = run_test(env, arm, test, small, log)
            r.pop("runs_detail", None)
            l1[arm][test] = r
    register_arm("P-abl", None)
    needs_edges = [c for c in caps if c["needs"] != "(none: control)"]
    controls = [c for c in caps if c["needs"] == "(none: control)"]
    return {
        "stripped_relationship_types": list(STRIPPED),
        "edges_before": intact["_edges_before"],
        "edges_deleted": removed,
        "capabilities": caps,
        "l1_rerun": l1,
        "summary": {
            "capabilities_needing_edges": len(needs_edges),
            "broken_by_ablation": sum(c["breaks_without_edges"] for c in needs_edges),
            "controls": len(controls),
            "controls_unaffected": sum(c["intact"]["passed"] and c["ablated"]["passed"] for c in controls),
            "intact_all_pass": all(c["intact"]["passed"] for c in caps),
        },
    }
