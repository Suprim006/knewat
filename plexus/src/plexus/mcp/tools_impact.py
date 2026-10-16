"""``impact``: the read-only blast radius of a source, a fact or a task (P9-b / P4).

Before ``quarantine`` or ``forget_source`` (which write), or before failing a task, an agent can ask what would be
affected. One call returns counts plus capped id lists of the affected facts, the agents / steps that read them, the
decisions and handoffs built on them and the tasks involved. Nothing is written and no ``READ`` edge is added: looking
at the damage must not make the damaged facts look used (same rule as ``facts_to_verify``). The traversal is the
level-wise, distinct-node expansion of ``lineage/impact_*`` and ``Relay.blocked_by_failure`` (a diamond lineage costs
its edges, not its paths).
"""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from plexus.lineage.service import DEFAULT_CASCADE_DEPTH, DEFAULT_IMPACT_DETAIL, MAX_DEPTH
from plexus.mcp.limits import AgentId, IdStr, Step
from plexus.mcp.runtime import MeteredClient, Outcome, Runtime, TenantState
from plexus.mcp.toolkit import ToolTable
from plexus.relay import service as relay_service
from plexus.relay.service import MAX_BLOCKED_DEPTH

MAX_ITEMS = 2000  # ids listed per category (totals are always exact)

IMPACT_TOOLS = ToolTable()
tool = IMPACT_TOOLS


def register_impact(mcp: MCPServer, rt: Runtime) -> list[str]:
    """Register the ``impact`` tool on ``mcp``; returns its name."""
    return IMPACT_TOOLS.register(mcp, rt)


@tool
def impact(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    kind: Annotated[
        Literal["source", "fact", "task"],
        Field(description="What to analyse: a 'source' (uri-registered), a 'fact', or a 'task'."),
    ],
    id: Annotated[IdStr, Field(description="The source_id, fact_id or task_id.")],
    depth: Annotated[
        int,
        Field(
            description=f"How many derivation / dependency hops to follow (default {DEFAULT_CASCADE_DEPTH}; "
            f"at most {MAX_DEPTH} for a source or fact, {MAX_BLOCKED_DEPTH} for a task).",
            ge=1,
            le=MAX_BLOCKED_DEPTH,
        ),
    ] = DEFAULT_CASCADE_DEPTH,
    max_items: Annotated[
        int, Field(description="Ids listed per category (totals are always exact).", ge=1, le=MAX_ITEMS)
    ] = DEFAULT_IMPACT_DETAIL,
    step: Step = None,
) -> Outcome:
    """Read-only blast radius: what is affected if a source or fact is wrong, or a task fails. Writes nothing.
    kind='source' or 'fact' returns the derived facts (count by status), the agents and steps that READ them,
    the decisions BASED_ON them, the tasks those decisions are FOR and the handoffs that CARRY them, with
    exact totals, earliest_at / latest_at (epoch ms) per category and the 5 earliest affected facts.
    kind='task' returns the unfinished tasks that transitively depend on it. Use it before quarantine_source,
    forget_source or fail_task to see the damage first."""
    if kind == "task":
        relay = ts.relay(m)
        if relay.task_status(id) is None:
            raise ToolError(f"impact: unknown task id: {id}")
        ids = relay.blocked_by_failure(id, depth=depth)
        return Outcome(
            {
                "impact": {
                    "kind": "task",
                    "id": id,
                    "depth": depth,
                    "tasks": {"total": len(ids), "ids": ids[:max_items]},
                    "truncated": len(ids) >= relay_service.MAX_BLOCKED_NODES,
                }
            }
        )
    if depth > MAX_DEPTH:
        raise ToolError(f"impact: depth must be between 1 and {MAX_DEPTH} for a {kind}")
    lin = ts.lineage(m)
    if lin is None:
        raise ToolError("impact: lineage is not available")
    return Outcome({"impact": lin.impact(kind, id, depth=depth, max_detail=max_items)})
