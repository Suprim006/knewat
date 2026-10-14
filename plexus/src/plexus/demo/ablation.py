"""``plexus demo ablation``: show, on a real tenant, which features stop working when the graph's edges are cut.

The tenant graph is copied (``GRAPH.COPY``) to ``<tenant>_ablated`` and ``DEPENDS_ON``, ``BASED_ON``, ``DERIVED_FROM``
and ``READ`` are deleted there (the same bounded ``crucible/strip_edges`` query the Crucible ablation uses). The same
feature probes then run on the intact tenant and on the stripped copy:

* read-only probes (``why``, ``knew_at``, ``who_knew``) run on the two graphs directly;
* probes that write (claims, ``forget_source``) run on throw-away copies of both, with the tasks put back to ``open``,
  so a finished recording has something to claim. The scratch copies are dropped when the command ends.

The original tenant is never written: its node and edge counts are checked before and after, and the command fails if
they differ. Controls (features that do not use those edges) must work on both sides, which shows the cut removed
the features it claims to and nothing else.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from redis.exceptions import ResponseError

from plexus.demo.inventory import inventory
from plexus.graph.client import GraphClient
from plexus.graph.tenancy import graph_name
from plexus.lineage import Lineage
from plexus.relay.service import Relay

STRIPPED = ("DEPENDS_ON", "BASED_ON", "DERIVED_FROM", "READ")
STRIP_BATCH = 1000
MAX_TASKS = 500  # the claim probe walks at most this many tasks
LEASE_MS = 600_000
SUFFIX_ABLATED = "_ablated"
SUFFIX_INTACT_SCRATCH = "_abl_i"
SUFFIX_ABLATED_SCRATCH = "_abl_x"
MAX_TENANT_LEN = 48 - len(SUFFIX_ABLATED)


@dataclass
class Row:
    feature: str
    needs: str  # the edge type it rests on; "" = control
    intact: str
    ablated: str
    intact_ok: bool
    ablated_ok: bool

    @property
    def control(self) -> bool:
        return not self.needs

    @property
    def broken(self) -> bool:
        return self.intact_ok and not self.ablated_ok


@dataclass
class Report:
    tenant: str
    ablated_tenant: str
    edges_deleted: dict[str, int]
    rows: list[Row] = field(default_factory=list)
    original_untouched: bool = True
    dropped: bool = False

    @property
    def needing(self) -> list[Row]:
        return [r for r in self.rows if not r.control]

    @property
    def controls(self) -> list[Row]:
        return [r for r in self.rows if r.control]

    @property
    def as_expected(self) -> bool:
        """Every feature works intact, every edge-dependent one breaks stripped, every control survives."""
        return (
            self.original_untouched
            and bool(self.needing)
            and all(r.intact_ok for r in self.rows)
            and all(r.broken for r in self.needing)
            and all(r.ablated_ok for r in self.controls)
        )


@dataclass
class Targets:
    decision: str | None = None
    reader: str | None = None
    source: str | None = None
    root_task: str | None = None


def copy_graph(client: GraphClient, src: str, dst: str) -> None:
    """``GRAPH.COPY src dst`` (replacing ``dst``). Nodes, edges, properties, vectors and indexes."""
    client.delete_graph(dst)
    client.db.connection.execute_command("GRAPH.COPY", src, dst)


def strip_edges(client: GraphClient, graph: str) -> dict[str, int]:
    """Delete every ``STRIPPED`` edge of ``graph`` in bounded batches; returns edges deleted per type."""
    deleted: dict[str, int] = dict.fromkeys(STRIPPED, 0)
    while True:
        results = client.rw_script(graph, "crucible/strip_edges", {"limit": STRIP_BATCH})
        total = 0
        for etype, res in zip(STRIPPED, results, strict=True):
            n = int(res.stats.get("relationships_deleted", 0)) if res is not None else 0
            deleted[etype] += n
            total += n
        if total == 0:
            return deleted


def pick_targets(client: GraphClient, graph: str) -> Targets:
    """The decision / reader / source / root task the probes use, chosen on the intact graph."""
    got = {r["kind"]: r["id"] for r in client.ro(graph, "demo/ablation_targets")}
    return Targets(
        decision=got.get("decision"),
        reader=got.get("reader"),
        source=got.get("source"),
        root_task=got.get("root_task"),
    )


def _edge_count(client: GraphClient, graph: str, etype: str) -> int:
    return sum(int(r["n"]) for r in client.ro(graph, "view/inventory_edges") if r["type"] == etype)


# ---------------------------------------------------------------------------------------------- read probes
def _read_probes(
    client: GraphClient, graph: str, tg: Targets, fact_id: str | None
) -> dict[str, tuple[int, str]]:
    """``{feature: (count, text)}`` for the read-only features on one graph."""
    lin = Lineage(client, graph)
    out: dict[str, tuple[int, str]] = {}
    if tg.decision:
        r = lin.why(tg.decision)
        n = len(r["facts"])
        out["why(decision)"] = (
            n,
            f"{n} supporting fact(s), {len(r['agents'])} agent(s), {len(r['sources'])} source(s)",
        )
    if tg.reader:
        r = lin.knew_at(tg.reader, 10**9)
        n = len(r["facts"])
        out["knew_at(agent, step)"] = (n, f"{n} fact(s) read by {tg.reader} (step {r['step_n']})")
    if fact_id:
        r = lin.who_knew(fact_id)
        n = len(r["agents"])
        out["who_knew(fact)"] = (n, f"{n} agent(s) read it")
    return out


def _fact_to_trace(client: GraphClient, graph: str, tg: Targets) -> str | None:
    """A fact the reader read, found on the intact graph (the stripped copy has no READ edges to find it by)."""
    if not tg.reader:
        return None
    facts = Lineage(client, graph).knew_at(tg.reader, 10**9)["facts"]
    return facts[0]["fact_id"] if facts else None


# ---------------------------------------------------------------------------------------------- write probes
def _write_probes(
    client: GraphClient, graph: str, tg: Targets, deps: dict[str, list[str]]
) -> dict[str, tuple[int, str, bool]]:
    """Features that write, on a scratch copy: ``{feature: (count, text, ok_on_its_own)}``."""
    client.rw(graph, "demo/ablation_reset_tasks", {"limit": MAX_TASKS})
    relay, lin = Relay(client, graph), Lineage(client, graph)
    out: dict[str, tuple[int, str, bool]] = {}
    if tg.root_task:
        n = len(relay.blocked_by_failure(tg.root_task))
        out["blocked_by_failure(task)"] = (n, f"{n} task(s) blocked behind {tg.root_task}", n > 0)
    if deps:
        for agent in ("ablation-a", "ablation-b"):
            relay.register_agent(agent, agent, "probe", "plexus-demo")
        claimed: list[str] = []
        for i in range(min(len(deps), MAX_TASKS) + 1):
            t = relay.claim_next_task("ablation-a" if i % 2 == 0 else "ablation-b", LEASE_MS)
            if t is None:
                break
            claimed.append(t["id"])
        unmet = [c for c in claimed if deps.get(c)]
        out["dependency-aware claim"] = (
            len(unmet),
            f"{len(claimed)} task(s) claimable on a fresh board, {len(unmet)} with unmet dependencies",
            bool(claimed) and not unmet,
        )
        dupes = len(claimed) - len(set(claimed))
        out["exclusive claims"] = (dupes, f"{len(claimed)} claim(s), {dupes} claimed twice", dupes == 0)
    if tg.source:
        r = lin.forget_source(tg.source)
        nf = len(r["fact_ids"])
        out["forget by source (cascade)"] = (
            nf,
            f"forgot {nf} fact(s), flagged {r['decisions_total']} decision(s)",
            nf > 0,
        )
    return out


# ---------------------------------------------------------------------------------------------- the run
def run_ablation(
    client: GraphClient, tenant: str, *, drop: bool = False, log: Callable[[str], None] = print
) -> Report:
    src = graph_name(tenant)
    if len(tenant) > MAX_TENANT_LEN:
        raise ValueError(
            f"tenant name too long for the '{SUFFIX_ABLATED}' copy (max {MAX_TENANT_LEN} characters)"
        )
    abl_tenant = tenant + SUFFIX_ABLATED
    abl = graph_name(abl_tenant)
    s_int, s_abl = graph_name(tenant + SUFFIX_INTACT_SCRATCH), graph_name(tenant + SUFFIX_ABLATED_SCRATCH)

    try:
        before = inventory(client, tenant)
    except ResponseError:  # the graph does not exist yet
        before = {"total_nodes": 0}
    if not before["total_nodes"]:
        raise SystemExit(
            f"tenant '{tenant}' has no data. Load one first: plexus demo replay acme-claude-sonnet --tenant {tenant}"
        )
    tg = pick_targets(client, src)
    deps = {r["id"]: list(r["deps"]) for r in client.ro(src, "demo/ablation_task_deps", {"limit": MAX_TASKS})}
    fact_id = _fact_to_trace(client, src, tg)

    log(f"copying {src} -> {abl} and deleting {', '.join(STRIPPED)} there ...")
    copy_graph(client, src, abl)
    deleted = strip_edges(client, abl)
    left = {t: _edge_count(client, abl, t) for t in STRIPPED}
    if any(left.values()):
        raise RuntimeError(f"edges left after stripping: {left}")
    rep = Report(tenant, abl_tenant, deleted)

    log("probing read-only features on both graphs ...")
    intact_r = _read_probes(client, src, tg, fact_id)
    ablated_r = _read_probes(client, abl, tg, fact_id)
    needs = {"why(decision)": "BASED_ON", "knew_at(agent, step)": "READ", "who_knew(fact)": "READ"}
    for name, (n_i, text_i) in intact_r.items():
        n_a, text_a = ablated_r[name]
        rep.rows.append(Row(name, needs[name], text_i, text_a, n_i > 0, n_a >= n_i))

    log("probing features that write, on throw-away copies ...")
    try:
        copy_graph(client, src, s_int)
        copy_graph(client, abl, s_abl)
        w_int = _write_probes(client, s_int, tg, deps)
        w_abl = _write_probes(client, s_abl, tg, deps)
    finally:
        client.delete_graph(s_int)
        client.delete_graph(s_abl)
    wneeds = {
        "blocked_by_failure(task)": "DEPENDS_ON",
        "dependency-aware claim": "DEPENDS_ON",
        "forget by source (cascade)": "DERIVED_FROM",
        "exclusive claims": "",
    }
    for name in (
        "dependency-aware claim",
        "blocked_by_failure(task)",
        "forget by source (cascade)",
        "exclusive claims",
    ):
        if name in w_int:
            n_i, text_i, ok_i = w_int[name]
            n_a, text_a, ok_a = w_abl[name]
            rep.rows.append(Row(name, wneeds[name], text_i, text_a, ok_i, ok_a))

    sup_i, sup_a = _edge_count(client, src, "SUPERSEDES"), _edge_count(client, abl, "SUPERSEDES")
    rep.rows.append(
        Row(
            "supersession history",
            "",
            f"{sup_i} SUPERSEDES edges",
            f"{sup_a} SUPERSEDES edges",
            True,
            sup_i == sup_a,
        )
    )

    after = inventory(client, tenant)
    rep.original_untouched = before == after
    if drop:
        client.delete_graph(abl)
        rep.dropped = True
    return rep


# ---------------------------------------------------------------------------------------------- output
def format_report(rep: Report) -> str:
    def cell(ok: bool, text: str) -> str:
        return f"{'works' if ok else 'BROKEN'}: {text}"

    order = [r for r in rep.rows if not r.control] + [r for r in rep.rows if r.control]
    rows = [("Feature", "Needs", f"Intact ({rep.tenant})", f"Edges removed ({rep.ablated_tenant})")]
    for r in order:
        rows.append(
            (r.feature, r.needs or "(control)", cell(r.intact_ok, r.intact), cell(r.ablated_ok, r.ablated))
        )
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    lines = []
    for i, row in enumerate(rows):
        lines.append("  ".join(c.ljust(widths[j]) for j, c in enumerate(row)).rstrip())
        if i == 0:
            lines.append("  ".join("-" * w for w in widths))
    gone = ", ".join(f"{t} x{n}" for t, n in rep.edges_deleted.items())
    broke = sum(r.broken for r in rep.needing)
    kept = sum(r.ablated_ok for r in rep.controls)
    lines += [
        "",
        f"edges deleted from {rep.ablated_tenant}: {gone}",
        f"{broke} of {len(rep.needing)} edge-dependent features break; {kept} of {len(rep.controls)} controls are unaffected",
        f"tenant '{rep.tenant}' was not modified: {'verified (node and edge counts equal before and after)' if rep.original_untouched else 'CHANGED, this is a bug'}",
        "the stripped copy was dropped"
        if rep.dropped
        else f"the stripped copy stays as tenant '{rep.ablated_tenant}': open it in the View and compare it with '{rep.tenant}'",
    ]
    return "\n".join(lines)


def to_dict(rep: Report) -> dict[str, Any]:
    return {
        "tenant": rep.tenant,
        "ablated_tenant": rep.ablated_tenant,
        "edges_deleted": rep.edges_deleted,
        "original_untouched": rep.original_untouched,
        "as_expected": rep.as_expected,
        "rows": [
            {
                "feature": r.feature,
                "needs": r.needs,
                "intact": r.intact,
                "ablated": r.ablated,
                "intact_ok": r.intact_ok,
                "ablated_ok": r.ablated_ok,
                "broken": r.broken,
            }
            for r in rep.rows
        ],
    }
