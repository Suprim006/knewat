"""Memory-strength tools (P7-K, D-012): pin / unpin, inspect, sweep and restore.

Forgetting in Plexus lowers a fact's *rank* only; these tools never delete. ``memory_sweep`` can move
low-activation, unprotected, non-suspect facts to ``dormant`` (dry run by default) and ``restore_fact`` brings one
back. Each tool is one service call; :meth:`Runtime.call` records the ``ToolCall`` and the agent's ``Step``.
Asking for a fact's strength is not a use of the fact: no ``READ`` edge is written.
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from plexus.activation import Activation
from plexus.mcp.limits import AgentId, IdStr, ScopeArg, Step
from plexus.mcp.runtime import MeteredClient, Outcome, Runtime, TenantState

MAX_SWEEP = 200


def _act(ts: TenantState, m: MeteredClient) -> Activation:
    return Activation(m, ts.graph)  # type: ignore[arg-type]


def register_memory(mcp: MCPServer, rt: Runtime) -> list[str]:
    """Register the memory-strength tools on ``mcp``; returns their names."""
    names: list[str] = []

    def tool(fn):
        names.append(fn.__name__)
        return mcp.tool()(fn)

    @tool
    async def pin_fact(
        agent_id: AgentId,
        fact_id: Annotated[
            IdStr, Field(description="The fact to protect from fading (from recall or assert_fact).")
        ],
        ctx: Context,
        step: Step = None,
    ) -> dict[str, Any]:
        """Pin a fact you know must stay prominent (a hard requirement, an owner decision). A pinned fact is never
        ranked below a neutral fact in recall and is never moved to dormant by memory_sweep. Undo with unpin_fact."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            if not _act(ts, m).pin(fact_id, True):
                raise LookupError(f"unknown fact id: {fact_id}")
            return Outcome({"fact_id": fact_id, "pinned": True}, updated=[("Fact", fact_id)])

        return await rt.call(ctx.headers, "pin_fact", agent_id, step, work)

    @tool
    async def unpin_fact(
        agent_id: AgentId,
        fact_id: Annotated[IdStr, Field(description="The fact to stop protecting.")],
        ctx: Context,
        step: Step = None,
    ) -> dict[str, Any]:
        """Remove the pin from a fact. It may still be protected for other reasons (a decision rests on it, a
        handoff carries it...): memory_strength lists them."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            if not _act(ts, m).pin(fact_id, False):
                raise LookupError(f"unknown fact id: {fact_id}")
            return Outcome({"fact_id": fact_id, "pinned": False}, updated=[("Fact", fact_id)])

        return await rt.call(ctx.headers, "unpin_fact", agent_id, step, work)

    @tool
    async def memory_strength(
        agent_id: AgentId,
        fact_id: Annotated[IdStr, Field(description="The fact to inspect.")],
        ctx: Context,
        step: Step = None,
    ) -> dict[str, Any]:
        """Show how strongly a fact ranks in recall and why: its activation (from creation, re-assertions,
        decisions, handoffs, uses, recalls and verifications), the neutral level, the ranking multiplier (never
        below the floor), why it is protected, and a one-line explanation. Read-only: asking does not count as
        using the fact."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            s = _act(ts, m).strength(fact_id)
            if s is None:
                raise LookupError(f"unknown fact id: {fact_id}")
            return Outcome({"strength": s})

        return await rt.call(ctx.headers, "memory_strength", agent_id, step, work)

    @tool
    async def memory_sweep(
        agent_id: AgentId,
        ctx: Context,
        scope: ScopeArg = "global",
        threshold: Annotated[
            float | None,
            Field(
                ge=-50.0,
                le=50.0,
                description="Activation below which an unprotected fact counts as faded. Default: the neutral "
                "level minus 2 (about a 60-day-old fact nobody has used).",
            ),
        ] = None,
        dry_run: Annotated[
            bool,
            Field(description="True (default) only lists what would move. False moves them to 'dormant'."),
        ] = True,
        limit: Annotated[
            int, Field(ge=1, le=MAX_SWEEP, description="Most facts to list or move.")
        ] = MAX_SWEEP,
        step: Step = None,
    ) -> dict[str, Any]:
        """Tidy a scope: list (dry_run=true, the default) or move to 'dormant' (dry_run=false) the faintest facts
        that nothing depends on. Never deletes. Facts a decision rests on, a handoff carries, that are pinned,
        contradicted, superseding, from a high-trust source, or suspect are never touched. Dormant facts are hidden
        from recall unless include_dormant=true; restore_fact undoes it."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            sid = ts.scope_id(scope, m, create=False)  # a sweep never creates a Scope
            if sid is None:
                return Outcome({"sweep": None, "note": "no such scope"})
            r = _act(ts, m).sweep(sid, threshold=threshold, dry_run=dry_run, limit=limit)
            for c in r["candidates"]:
                c["activation"] = round(c["activation"], 3) if c["activation"] != float("-inf") else None
            r["threshold"] = round(r["threshold"], 3)
            return Outcome({"sweep": r}, updated=[("Fact", f) for f in r["moved"]])

        return await rt.call(ctx.headers, "memory_sweep", agent_id, step, work)

    @tool
    async def restore_fact(
        agent_id: AgentId,
        fact_id: Annotated[IdStr, Field(description="A dormant fact to bring back.")],
        ctx: Context,
        step: Step = None,
    ) -> dict[str, Any]:
        """Bring a fact that memory_sweep moved to 'dormant' back to active, exactly as it was. A fact that is not
        dormant is left alone (restored=false)."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            r = _act(ts, m).restore(fact_id)
            if r is None:
                raise LookupError(f"unknown fact id: {fact_id}")
            return Outcome(r, updated=[("Fact", fact_id)] if r["restored"] else [])

        return await rt.call(ctx.headers, "restore_fact", agent_id, step, work)

    return names
