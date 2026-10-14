"""Lineage MCP tools, registered only when ``plexus.lineage`` exists (P2-D merges separately).

Contract assumed from the P2-D spec: ``plexus.lineage.Lineage(client, graph)`` with any of the methods
``why(node_id)``, ``why_recalled(recall_id)``, ``who_knew(fact_id)``, ``knew_at(agent_id, step_n)``,
``as_of(subject, predicate, t, scope_id)``, ``forget_source(source_id, mode='forget')`` and (optionally)
``record_step(agent_id, n) -> step_id``. A method that is missing is simply not exposed as a tool.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from plexus.mcp.runtime import MeteredClient, Outcome, Runtime, TenantState

log = logging.getLogger("plexus.mcp")

AgentId = Annotated[str, Field(description="Your stable agent id.", min_length=1)]
Step = Annotated[int | None, Field(description="Optional: your own step counter.")]


def lineage_available() -> bool:
    if sys.modules.get("plexus.lineage") is not None:
        return True
    try:
        return importlib.util.find_spec("plexus.lineage") is not None
    except (ImportError, ValueError):
        return False


def _lineage(ts: TenantState, m: MeteredClient):
    mod = importlib.import_module("plexus.lineage")
    return mod.Lineage(m, ts.graph)


def _jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, list | tuple | set):
        return [_jsonable(v) for v in x]
    return x if isinstance(x, str | int | float | bool | type(None)) else str(x)


def register_lineage(mcp: MCPServer, rt: Runtime) -> list[str]:
    """Register whichever Lineage tools the installed ``plexus.lineage`` provides. Returns their names."""
    if not lineage_available():
        return []
    mod = importlib.import_module("plexus.lineage")
    cls = getattr(mod, "Lineage", None)
    if cls is None:
        log.warning("plexus.lineage has no Lineage class; Lineage tools not registered")
        return []
    has = {
        n for n in ("why", "why_recalled", "who_knew", "knew_at", "as_of", "forget_source") if hasattr(cls, n)
    }
    names: list[str] = []

    def tool(fn):
        names.append(fn.__name__)
        return mcp.tool()(fn)

    if "why" in has:

        @tool
        async def why(
            agent_id: AgentId,
            node_id: Annotated[str, Field(description="A decision id or a fact id.")],
            ctx: Context,
            step: Step = None,
        ) -> dict[str, Any]:
            """Explain WHY: the graph paths from a decision (or fact) to the facts, agents, steps and sources
            it rests on."""

            def work(ts: TenantState, m: MeteredClient) -> Outcome:
                return Outcome({"why": _jsonable(_lineage(ts, m).why(node_id))})

            return await rt.call(ctx.headers, "why", agent_id, step, work)

    if "why_recalled" in has:

        @tool
        async def why_recalled(
            agent_id: AgentId,
            recall_id: Annotated[str, Field(description="A recall id.")],
            ctx: Context,
            step: Step = None,
        ) -> dict[str, Any]:
            """Explain why a past recall returned the facts it did (ranks, scores, provenance)."""

            def work(ts: TenantState, m: MeteredClient) -> Outcome:
                return Outcome({"why_recalled": _jsonable(_lineage(ts, m).why_recalled(recall_id))})

            return await rt.call(ctx.headers, "why_recalled", agent_id, step, work)

    if "who_knew" in has:

        @tool
        async def who_knew(
            agent_id: AgentId,
            fact_id: Annotated[str, Field(description="A fact id.")],
            ctx: Context,
            step: Step = None,
        ) -> dict[str, Any]:
            """Which agents asserted or read a fact, and at which step."""

            def work(ts: TenantState, m: MeteredClient) -> Outcome:
                return Outcome({"who_knew": _jsonable(_lineage(ts, m).who_knew(fact_id))})

            return await rt.call(ctx.headers, "who_knew", agent_id, step, work)

    if "knew_at" in has:

        @tool
        async def knew_at(
            agent_id: AgentId,
            subject_agent: Annotated[str, Field(description="The agent whose knowledge to reconstruct.")],
            step_n: Annotated[int, Field(description="The step number.")],
            ctx: Context,
            step: Step = None,
        ) -> dict[str, Any]:
            """What a given agent knew (facts read and still valid) and wrote up to step N."""

            def work(ts: TenantState, m: MeteredClient) -> Outcome:
                return Outcome({"knew_at": _jsonable(_lineage(ts, m).knew_at(subject_agent, step_n))})

            return await rt.call(ctx.headers, "knew_at", agent_id, step, work)

    if "as_of" in has:

        @tool
        async def as_of(
            agent_id: AgentId,
            subject: Annotated[str, Field(description="Fact subject.")],
            predicate: Annotated[str, Field(description="Fact attribute.")],
            t: Annotated[int, Field(description="Epoch milliseconds.")],
            ctx: Context,
            scope: Annotated[str, Field(description="Scope id (default: global).")] = "global",
            step: Step = None,
        ) -> dict[str, Any]:
            """The value a (subject, predicate) had at time t."""

            def work(ts: TenantState, m: MeteredClient) -> Outcome:
                sid = ts.scope_id(scope, m)
                return Outcome({"as_of": _jsonable(_lineage(ts, m).as_of(subject, predicate, t, sid))})

            return await rt.call(ctx.headers, "as_of", agent_id, step, work)

    if "forget_source" in has:

        @tool
        async def forget_source(
            agent_id: AgentId,
            source_id: Annotated[str, Field(description="Source whose derived facts should be forgotten.")],
            ctx: Context,
            step: Step = None,
        ) -> dict[str, Any]:
            """Forget a source and every fact derived from it (cascade). Decisions based on them are flagged."""

            def work(ts: TenantState, m: MeteredClient) -> Outcome:
                r = _jsonable(_lineage(ts, m).forget_source(source_id))
                return Outcome({"forgotten": r})

            return await rt.call(ctx.headers, "forget_source", agent_id, step, work)

    return names
