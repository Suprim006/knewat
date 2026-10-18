"""Soft-duplicate MCP tools (P9-c B2): ``confirm_duplicate`` / ``reject_duplicate``.

``assert_fact`` never merges a value it is not sure about; when a new fact looks like an existing one but not
enough to merge, it stores the new fact AND a ``DUPLICATES_MAYBE`` link and returns ``possible_duplicates``
(``recall`` hits carry ``maybe_duplicate_of``). The agent that knows decides with these two tools. Knewat makes no
LLM call. Both tools are ordinary write tools: a ``ToolCall`` and the agent's ``Step`` (``WROTE`` both facts).
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from knewat.engram.dedup import Dedup
from knewat.mcp.limits import AgentId, IdStr, Step
from knewat.mcp.runtime import LINK_CHUNK, MeteredClient, Outcome, Runtime, TenantState
from knewat.mcp.toolkit import ToolTable

DEDUP_TOOLS = ToolTable()
tool = DEDUP_TOOLS


def register_dedup(mcp: MCPServer, rt: Runtime) -> list[str]:
    """Register the 2 soft-duplicate tools on ``mcp``; returns their names."""
    return DEDUP_TOOLS.register(mcp, rt)


def _wrote(fact_ids: list[str]):
    ids = list(dict.fromkeys(fact_ids))

    def after(lin, step_id):  # noqa: ANN001 - Outcome.after hook
        for i in range(0, len(ids), LINK_CHUNK):
            lin.link_step(step_id, wrote_ids=ids[i : i + LINK_CHUNK])
        return None

    return after


@tool
def confirm_duplicate(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    new_id: Annotated[
        IdStr,
        Field(description="The newer fact (the fact_id assert_fact returned, with possible_duplicates)."),
    ],
    old_id: Annotated[IdStr, Field(description="The older fact it duplicates (from possible_duplicates).")],
    step: Step = None,
) -> Outcome:
    """Say that two facts flagged as possible duplicates are the SAME statement. The newer fact becomes a duplicate
    of the older one: recall returns the older one only, and whoever asserted the newer one now counts as an asserter
    of the older one (their wording is kept on the edge). Nothing is deleted; reject_duplicate on the same pair undoes
    it. Only call this when the two really say the same thing: 'enabled' and 'not enabled' do not."""
    r = Dedup(m, ts.graph).confirm_duplicate(new_id, old_id)
    return Outcome(
        r,
        updated=[("Fact", new_id), ("Fact", old_id)] if r["merged"] else [],
        after=_wrote([new_id, old_id]) if r["merged"] else None,
    )


@tool
def reject_duplicate(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    new_id: Annotated[IdStr, Field(description="The newer fact of the possible-duplicate pair.")],
    old_id: Annotated[IdStr, Field(description="The older fact of the pair.")],
    step: Step = None,
) -> Outcome:
    """Say that two facts flagged as possible duplicates are DIFFERENT statements: the possible_duplicates link is
    removed and both facts stay as they are. On a pair you confirmed earlier this undoes the merge instead (the newer
    fact is current again)."""
    r = Dedup(m, ts.graph).reject_duplicate(new_id, old_id)
    changed = r["rejected"] or r["undone"]
    return Outcome(
        r,
        updated=[("Fact", new_id), ("Fact", old_id)] if changed else [],
        after=_wrote([new_id, old_id]) if r["undone"] else None,
    )
