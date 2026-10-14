"""P: the Plexus arm. One tenant graph per run, driven through the real service layer.

``PlexusBackend`` calls the same code the MCP tools call (``Engram``, ``Relay``, ``Lineage``) and, in ``mode="mcp"``,
goes through ``Runtime._run`` so every call also opens a ``Step`` and writes a ``ToolCall`` exactly as the server
does (the only things left out are the JSON transport and the network hop to the MCP server).

Modes
-----
``service`` (arm ``P``)    Engram/Relay/Lineage calls. Memory, decision and handoff calls also open a Step and link
                           READ/WROTE edges (so ``knew_at`` / ``why`` work); claim/heartbeat/complete do not.
``mcp`` (arm ``P-mcp``)    every call goes through ``Runtime._run``: Step + READ/WROTE + ToolCall per call.

``ablate()`` deletes the DEPENDS_ON, BASED_ON, DERIVED_FROM and READ relationships (D-001) to show what breaks.
Server-side execution time of the last call (``run_time_ms`` summed over its queries, as the ToolCall stores it) is
available from :meth:`last_server_ms` for the L4 report.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from falkordb import FalkorDB
from mcp.server.mcpserver.exceptions import ToolError

from plexus.crucible import api
from plexus.crucible.api import ClaimConflict, UnknownReference
from plexus.embed import Embedder, get_embedder
from plexus.engram.errors import UnknownReference as EngramUnknown
from plexus.graph.client import GraphClient
from plexus.graph.tenancy import graph_name
from plexus.mcp.runtime import MeteredClient, Outcome, Runtime, TenantState
from plexus.relay import errors as relay_errors

POOL = int(os.environ.get("CRUCIBLE_POOL", "512"))


def _client(host: str | None, port: int | None) -> GraphClient:
    """A GraphClient whose connection pool fits the benchmark's worker threads.

    redis-py's default pool holds 100 connections, so 200 threads sharing one client fail with
    ``MaxConnectionsError`` (a client-side limit, not a server one; the MCP server caps concurrent tool calls
    with its thread limiter). The harness raises the pool; nothing else about the client changes.
    """
    c = GraphClient(host=host, port=port)
    old = c.db
    c.db = FalkorDB(host=c.host, port=c.port, password=_password(), max_connections=POOL)
    old.connection.close()
    return c


def _password() -> str | None:
    return os.environ.get("FALKORDB_PASSWORD") or None


TRACKED = frozenset({"assert_fact", "recall", "record_decision", "handoff", "remember_episode"})
STRIP_BATCH = 5000


def _ref(fid: str) -> tuple[str, str]:
    return ("Fact", fid)


class PlexusBackend:
    name = "P"
    label = "Plexus"
    capabilities = frozenset(
        {"why", "knew_at", "as_of", "semantic_dedupe", "contradictions", "forget_cascade", "dependencies"}
    )
    isolation = (
        "one FalkorDB graph per tenant (plexus_t_<tenant>); the tenant is bound at construction, never taken from "
        "a tool argument, and validated against ^[a-z0-9_]{1,48}$"
    )

    def __init__(
        self,
        tenant: str,
        host: str | None = None,
        port: int | None = None,
        embedder: Embedder | str | None = None,
        mode: str = "service",
        client: GraphClient | None = None,
    ):
        if mode not in ("service", "mcp"):
            raise ValueError("mode must be 'service' or 'mcp'")
        try:
            self.graph = graph_name(tenant)  # raises ValueError for anything that is not a tenant name
        except ValueError as exc:
            raise api.InvalidTenant(str(exc)) from None
        self.tenant = tenant
        self.mode = mode
        self.name = "P" if mode == "service" else "P-mcp"
        self.label = "Plexus" if mode == "service" else "Plexus (MCP path)"
        self._owns_client = client is None
        self.client = client or _client(host, port)
        self.embedder: Embedder = embedder if isinstance(embedder, Embedder) else get_embedder(embedder)
        self.rt = Runtime(client=self.client, embedder=self.embedder, stdio_tenant=tenant)
        self.ts: TenantState = self.rt.state(tenant)  # applies the schema once
        self._tls = threading.local()
        self._steps_enabled = True

    # -- plumbing -----------------------------------------------------------------------------------------
    def last_server_ms(self) -> float:
        """Server-side ``run_time_ms`` summed over the queries of this thread's last call."""
        return float(getattr(self._tls, "server_ms", 0.0))

    def _call(
        self, tool: str, agent_id: str, work: Callable[[TenantState, MeteredClient], Outcome]
    ) -> dict[str, Any]:
        holder: dict[str, MeteredClient] = {}

        def wrapped(ts: TenantState, m: MeteredClient) -> Outcome:
            holder["m"] = m
            return work(ts, m)

        try:
            if self.mode == "mcp":
                data = self.rt._run(self.tenant, tool, agent_id, None, wrapped)
            else:
                m = MeteredClient(self.client)
                wrapped_out = wrapped(self.ts, m)
                data = dict(wrapped_out.data)
                if self._steps_enabled and tool in TRACKED:
                    step_id = self.rt._open_step(self.ts, agent_id, None, self._now())
                    data.update(self.rt._attach(self.ts, step_id, wrapped_out))
        except ToolError as exc:  # e.g. an invalid scope spec: a caller mistake, like a ValueError
            raise ValueError(str(exc)) from None
        except relay_errors.ClaimConflict as exc:
            raise ClaimConflict(str(exc)) from None
        except (relay_errors.UnknownReference, EngramUnknown) as exc:
            raise UnknownReference(str(exc)) from None
        finally:
            m = holder.get("m")
            self._tls.server_ms = m.run_time_ms if m is not None else 0.0
        return data

    @staticmethod
    def _now() -> int:
        from plexus.crucible.util import now_ms

        return now_ms()

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    # -- agents ---------------------------------------------------------------------------------------------
    def register_agent(self, agent_id: str, role: str = "") -> None:
        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            r = ts.relay(m).register_agent(agent_id, agent_id, role, "crucible")
            return Outcome({"agent": r}, updated=[("Agent", agent_id)])

        self._call("register_agent", agent_id, work)

    # -- memory -----------------------------------------------------------------------------------------------
    def remember_episode(self, agent_id: str, text: str, step: int | None = None) -> str:
        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            eng = ts.engram(m)
            sid = eng.start_session(agent_id, "", harness="crucible")
            eid = eng.remember_episode(sid, "note", text, step)
            return Outcome({"episode_id": eid}, created=[("Episode", eid)], updated=[("Session", sid)])

        return self._call("remember_episode", agent_id, work)["episode_id"]

    def add_source(self, uri: str, kind: str = "doc", trust: float = 1.0) -> str:
        from plexus.lineage import Lineage

        m = MeteredClient(self.client)
        return Lineage(m, self.graph).create_source(uri, kind, trust)  # type: ignore[arg-type]

    def assert_fact(
        self,
        agent_id: str,
        subject: str,
        predicate: str,
        value: str,
        scope: str = "global",
        source_id: str | None = None,
        derived_from: Sequence[str] = (),
        confidence: float = 1.0,
        supersede: bool = False,
        now: int | None = None,
    ) -> dict[str, Any]:
        origins = list(dict.fromkeys(derived_from))

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            sid = ts.scope_id(scope, m)
            if origins:  # derived_from is a second statement: check the ids first so a bad id writes nothing
                have = {r["id"] for r in m.ro(self.graph, "lineage/existing_ids", {"ids": origins})}
                missing = [o for o in origins if o not in have]
                if missing:
                    raise UnknownReference(f"unknown origin id: {', '.join(missing)}")
            r = ts.engram(m).assert_fact(
                subject, predicate, value, sid, agent_id,
                source_id=source_id, confidence=confidence, supersede=supersede, now=now,
            )  # fmt: skip
            if origins:
                ts.lineage(m).derive_from(r["fact_id"], origins)
            created = [] if r["duplicate_of"] else [_ref(r["fact_id"])]
            updated = [_ref(f) for f in r["superseded"]]
            if r["duplicate_of"]:
                updated.append(_ref(r["duplicate_of"]))
            return Outcome({**r, "scope_id": sid}, created=created, updated=updated, assert_result=r)

        d = self._call("assert_fact", agent_id, work)
        return {
            "fact_id": d["fact_id"],
            "duplicate_of": d["duplicate_of"],
            "superseded": list(d["superseded"]),
            "contradicts": list(d["contradicts"]),
        }

    def recall(
        self, agent_id: str, query: str, scope: str = "global", k: int = 8, as_of: int | None = None
    ) -> list[dict[str, Any]]:
        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            sid = ts.scope_id(scope, m)
            hits = ts.engram(m).recall(query, sid, k=k, as_of=as_of)

            def record(lin: Any, step_id: str | None) -> dict[str, Any]:
                return {"recall_id": lin.record_recall(agent_id, step_id, query, sid, k, hits)}

            return Outcome({"facts": hits}, after=record)

        d = self._call("recall", agent_id, work)
        return [
            {
                "fact_id": h["fact_id"],
                "text": h["text"],
                "entity": h["entity"],
                "predicate": h["predicate"],
                "value": h["value"],
                "status": h["status"],
                "score": float(h["score"]),
            }
            for h in d["facts"]
        ]

    def forget_source(self, source_id: str) -> dict[str, Any]:
        from plexus.lineage import Lineage
        from plexus.lineage.service import UnknownNode

        m = MeteredClient(self.client)
        try:
            r = Lineage(m, self.graph).forget_source(source_id)  # type: ignore[arg-type]
        except UnknownNode as exc:
            raise UnknownReference(str(exc)) from None
        return {"source_id": source_id, "fact_ids": list(r["fact_ids"])}

    def facts(self, subject: str, predicate: str, scope: str = "global") -> list[dict[str, Any]]:
        m = MeteredClient(self.client)
        sid = self.ts.scope_id(scope, m)
        rows = self.ts.engram(m).fact_history(subject, predicate, sid)
        return [
            {
                "fact_id": r["fact_id"],
                "value": r["value"],
                "status": r["status"],
                "valid_from": r["valid_from"],
                "valid_to": r["valid_to"],
                "asserted_by": list(r["asserted_by"]),
                "supersedes": sorted(r["supersedes"]),
                "contradicts": sorted(r["contradicts"]),
            }
            for r in rows
        ]

    def as_of(self, subject: str, predicate: str, t: int, scope: str = "global") -> dict[str, Any] | None:
        m = MeteredClient(self.client)
        sid = self.ts.scope_id(scope, m)
        r = self.ts.lineage(m).as_of(subject, predicate, t, sid)
        if r is None:
            return None

        def one(x: dict[str, Any]) -> dict[str, Any]:
            return {k: x[k] for k in ("fact_id", "value", "status", "valid_from", "valid_to")}

        out = one(r)
        out["also_valid"] = [one(x) for x in r["also_valid"]]
        return out

    # -- coordination -------------------------------------------------------------------------------------------
    def create_tasks(self, tasks: Sequence[dict[str, Any]]) -> list[str]:
        out: list[str] = []
        # the Relay API takes at most 500 tasks per call; a larger DAG is created batch by batch (in order)
        for i in range(0, len(tasks), 500):
            chunk = list(tasks[i : i + 500])

            def work(ts: TenantState, m: MeteredClient, chunk=chunk) -> Outcome:
                ids = ts.relay(m).create_tasks(chunk)
                return Outcome({"task_ids": ids}, created=[("Task", x) for x in ids])

            try:
                out.extend(self._call("create_tasks", "crucible", work)["task_ids"])
            except relay_errors.InvalidDag as exc:
                raise ValueError(str(exc)) from None
            except relay_errors.DuplicateTask as exc:
                raise ValueError(str(exc)) from None
        return out

    def claim_next_task(
        self, agent_id: str, lease_ms: int = 60_000, now: int | None = None
    ) -> dict[str, Any] | None:
        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            t = ts.relay(m).claim_next_task(agent_id, lease_ms, now)
            if t is None:
                return Outcome({"task": None})
            return Outcome({"task": t}, updated=[("Task", t["id"])])

        t = self._call("claim_next_task", agent_id, work)["task"]
        if t is None:
            return None
        return {
            "id": t["id"],
            "title": t["title"],
            "priority": t["priority"],
            "version": t["version"],
            "lease_until": t["lease_until"],
            "reclaimed_from": t["reclaimed_from"],
        }

    def heartbeat(self, agent_id: str, task_id: str, lease_ms: int = 60_000, now: int | None = None) -> bool:
        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            ok = ts.relay(m).heartbeat(agent_id, task_id, lease_ms, now)
            return Outcome({"alive": ok}, updated=[("Task", task_id)] if ok else [])

        return bool(self._call("heartbeat", agent_id, work)["alive"])

    def complete_task(
        self, agent_id: str, task_id: str, expected_version: int, artifacts: Sequence[dict[str, Any]] = ()
    ) -> dict[str, Any]:
        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            r = ts.relay(m).complete_task(agent_id, task_id, expected_version, list(artifacts))
            return Outcome(
                r, created=[("Artifact", a) for a in r["artifact_ids"]], updated=[("Task", task_id)]
            )

        d = self._call("complete_task", agent_id, work)
        return {k: d[k] for k in ("id", "status", "version", "artifact_ids")}

    def handoff(
        self,
        agent_id: str,
        to_agent: str,
        task_id: str,
        note: str,
        artifact_ids: Iterable[str] = (),
        fact_ids: Iterable[str] = (),
    ) -> str:
        facts = list(fact_ids)

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            hid = ts.relay(m).handoff(agent_id, to_agent, task_id, note, list(artifact_ids), facts)
            return Outcome({"handoff_id": hid}, created=[("Handoff", hid)], read_ids=facts)

        return self._call("handoff", agent_id, work)["handoff_id"]

    def record_decision(
        self, agent_id: str, task_id: str, text: str, based_on_fact_ids: Iterable[str] = ()
    ) -> str:
        facts = list(based_on_fact_ids)

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            did = ts.relay(m).record_decision(agent_id, task_id, text, facts)
            return Outcome({"decision_id": did}, created=[("Decision", did)], read_ids=facts)

        return self._call("record_decision", agent_id, work)["decision_id"]

    def task_status(self, task_id: str) -> dict[str, Any] | None:
        st = self.ts.relay(MeteredClient(self.client)).task_status(task_id)
        if st is None:
            return None
        return {
            "id": st["id"],
            "title": st["title"],
            "status": st["status"],
            "claimed_by": st["claimed_by"],
            "version": st["version"],
            "lease_until": st["lease_until"],
            "dependencies": [dict(d) for d in st["dependencies"]],
        }

    def list_tasks(self) -> list[dict[str, Any]]:
        rows = self.client.ro(self.graph, "crucible/list_tasks", {"limit": 100_000})
        return [{k: r[k] for k in ("id", "status", "claimed_by", "version", "lease_until")} for r in rows]

    def blocked_by_failure(self, task_id: str) -> list[str]:
        return self.ts.relay(MeteredClient(self.client)).blocked_by_failure(task_id)

    # -- lineage ----------------------------------------------------------------------------------------------------
    def why(self, node_id: str) -> dict[str, Any]:
        from plexus.lineage.service import UnknownNode

        try:
            r = self.ts.lineage(MeteredClient(self.client)).why(node_id)
        except UnknownNode as exc:
            raise UnknownReference(str(exc)) from None
        facts = []
        for f in r["facts"]:
            props = f.get("props") or {}
            facts.append(
                {
                    "id": f["id"],
                    "value": props.get("value"),
                    "status": props.get("status"),
                    "asserted_by": list(f["asserted_by"]),
                    "sources": list(f["sources"]),
                    "supersedes": list(f["supersedes"]),
                    "superseded_by": list(f["superseded_by"]),
                    "contradicts": list(f["contradicts"]),
                }
            )
        return {
            "root": r["root"],
            "kind": r["kind"],
            "facts": facts,
            "agents": r["agents"],
            "sources": r["sources"],
        }

    def knew_at(self, agent_id: str, step_n: int) -> dict[str, Any]:
        return self.ts.lineage(MeteredClient(self.client)).knew_at(agent_id, step_n)

    def who_knew(self, fact_id: str) -> dict[str, Any]:
        """Agents whose Steps READ the fact (Plexus-only lineage read; the ablation probes use it)."""
        from plexus.lineage.service import UnknownNode

        try:
            return self.ts.lineage(MeteredClient(self.client)).who_knew(fact_id)
        except UnknownNode as exc:
            raise UnknownReference(str(exc)) from None

    # -- ablation (D-001) ---------------------------------------------------------------------------------------------
    def ablate(self) -> dict[str, int]:
        """Delete every DEPENDS_ON, BASED_ON, DERIVED_FROM and READ relationship. Returns edges deleted per type."""
        types = ("DEPENDS_ON", "BASED_ON", "DERIVED_FROM", "READ")
        deleted: dict[str, int] = dict.fromkeys(types, 0)
        while True:
            results = self.client.rw_script(self.graph, "crucible/strip_edges", {"limit": STRIP_BATCH})
            round_total = 0
            for t, res in zip(types, results, strict=True):
                n = int(res.stats.get("relationships_deleted", 0)) if res is not None else 0
                deleted[t] += n
                round_total += n
            if round_total == 0:
                return deleted

    def edge_counts(self) -> dict[str, int]:
        """Relationship counts by type (verification read, via the View inventory query)."""
        rows = self.client.ro(self.graph, "view/inventory_edges")
        return {r["type"]: int(r["n"]) for r in rows}

    def drop(self) -> None:
        """Delete this tenant's graph (benchmark cleanup)."""
        self.client.delete_graph(self.graph)
