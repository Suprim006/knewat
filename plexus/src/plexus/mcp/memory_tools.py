"""Memory-strength tools (P7-K, D-012): pin / unpin, inspect, sweep and restore.

Forgetting in Plexus lowers a fact's *rank* only; these tools never delete. ``memory_sweep`` can move
low-activation, unprotected, non-suspect facts to ``dormant`` (dry run by default) and ``restore_fact`` brings one
back. Each tool is one service call; :meth:`Runtime.call` records the ``ToolCall`` and the agent's ``Step``.
Asking for a fact's strength is not a use of the fact: no ``READ`` edge is written.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from plexus.activation import Activation
from plexus.mcp.limits import AgentId, IdStr, ScopeArg, Step
from plexus.mcp.runtime import MeteredClient, Outcome, Runtime, TenantState
from plexus.mcp.toolkit import ToolTable

MAX_SWEEP = 200

MEMORY_TOOLS = ToolTable()
tool = MEMORY_TOOLS


def _act(ts: TenantState, m: MeteredClient) -> Activation:
    return Activation(m, ts.graph)  # type: ignore[arg-type]


def register_memory(mcp: MCPServer, rt: Runtime) -> list[str]:
    """Register the memory-strength tools on ``mcp``; returns their names."""
    return MEMORY_TOOLS.register(mcp, rt)


def _set_pin(ts: TenantState, m: MeteredClient, fact_id: str, pinned: bool) -> Outcome:
    if not _act(ts, m).pin(fact_id, pinned):
        raise LookupError(f"unknown fact id: {fact_id}")
    return Outcome({"fact_id": fact_id, "pinned": pinned}, updated=[("Fact", fact_id)])


@tool
def pin_fact(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    fact_id: Annotated[
        IdStr, Field(description="The fact to protect from fading (from recall or assert_fact).")
    ],
    step: Step = None,
) -> Outcome:
    """Pin a fact you know must stay prominent (a hard requirement, an owner decision). A pinned fact is never
    ranked below a neutral fact in recall and is never moved to dormant by memory_sweep. Undo with unpin_fact."""
    return _set_pin(ts, m, fact_id, True)


@tool
def unpin_fact(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    fact_id: Annotated[IdStr, Field(description="The fact to stop protecting.")],
    step: Step = None,
) -> Outcome:
    """Remove the pin from a fact. It may still be protected for other reasons (a decision rests on it, a
    handoff carries it...): memory_strength lists them."""
    return _set_pin(ts, m, fact_id, False)


@tool
def memory_strength(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    fact_id: Annotated[IdStr, Field(description="The fact to inspect.")],
    step: Step = None,
) -> Outcome:
    """Show how strongly a fact ranks in recall and why: its activation (from creation, re-assertions,
    decisions, handoffs, uses, recalls and verifications), the neutral level, the ranking multiplier (never
    below the floor), why it is protected, and a one-line explanation. Read-only: asking does not count as
    using the fact."""
    s = _act(ts, m).strength(fact_id)
    if s is None:
        raise LookupError(f"unknown fact id: {fact_id}")
    return Outcome({"strength": s})


@tool
def memory_sweep(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
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
        bool, Field(description="True (default) only lists what would move. False moves them to 'dormant'.")
    ] = True,
    limit: Annotated[int, Field(ge=1, le=MAX_SWEEP, description="Most facts to list or move.")] = MAX_SWEEP,
    step: Step = None,
) -> Outcome:
    """Tidy a scope: list (dry_run=true, the default) or move to 'dormant' (dry_run=false) the faintest facts
    that nothing depends on. Never deletes. Facts a decision rests on, a handoff carries, that are pinned,
    contradicted, superseding, from a high-trust source, or suspect are never touched. Dormant facts are hidden
    from recall unless include_dormant=true; restore_fact undoes it."""
    sid = ts.scope_id(scope, m, create=False)  # a sweep never creates a Scope
    if sid is None:
        return Outcome({"sweep": None, "note": "no such scope"})
    r = _act(ts, m).sweep(sid, threshold=threshold, dry_run=dry_run, limit=limit)
    for c in r["candidates"]:
        c["activation"] = round(c["activation"], 3) if c["activation"] != float("-inf") else None
    r["threshold"] = round(r["threshold"], 3)
    return Outcome({"sweep": r}, updated=[("Fact", f) for f in r["moved"]])


@tool
def restore_fact(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    fact_id: Annotated[IdStr, Field(description="A dormant fact to bring back.")],
    step: Step = None,
) -> Outcome:
    """Bring a fact that memory_sweep moved to 'dormant' back to active, exactly as it was. A fact that is not
    dormant is left alone (restored=false)."""
    r = _act(ts, m).restore(fact_id)
    if r is None:
        raise LookupError(f"unknown fact id: {fact_id}")
    return Outcome(r, updated=[("Fact", fact_id)] if r["restored"] else [])
