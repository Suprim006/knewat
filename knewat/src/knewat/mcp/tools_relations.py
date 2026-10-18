"""``assert_relation``: typed relations between entities (P9-b / P2); ``recall(hops)`` follows them.

``assert_relation(subject, kind, object, scope)`` writes ``(Entity)-[:RELATES {kind, scope_id}]->(Entity)`` (idempotent).
The relations are only as good as what agents write: Plexus makes no LLM call to extract them.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from plexus.mcp.limits import AgentId, Name, NameReq, ScopeArg, Step
from plexus.mcp.runtime import MeteredClient, Outcome, Runtime, TenantState
from plexus.mcp.toolkit import ToolTable

RELATION_TOOLS = ToolTable()
tool = RELATION_TOOLS


def register_relations(mcp: MCPServer, rt: Runtime) -> list[str]:
    """Register ``assert_relation`` on ``mcp``; returns its name."""
    return RELATION_TOOLS.register(mcp, rt)


@tool
def assert_relation(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    subject: Annotated[NameReq, Field(description="The first entity, e.g. 'Payment Service'.")],
    kind: Annotated[
        NameReq,
        Field(description="How it relates, e.g. 'depends on', 'owned by', 'backed up by' (max 128 chars)."),
    ],
    object: Annotated[NameReq, Field(description="The second entity, e.g. 'Ledger DB'.")],
    scope: ScopeArg = "global",
    subject_kind: Annotated[Name, Field(description="Entity kind of the subject, e.g. 'service'.")] = "thing",
    object_kind: Annotated[Name, Field(description="Entity kind of the object, e.g. 'database'.")] = "thing",
    step: Step = None,
) -> Outcome:
    """Record that two things are related (subject --kind--> object), e.g. 'Payment Service' 'depends on'
    'Ledger DB'. Safe to repeat. recall(hops=1 or 2) then also returns the facts of entities that are
    1-2 relations away from what the question matched, even when they share no words with it. Entities are
    matched like assert_fact's subject. Returns created (false when the relation already existed) and the
    two entity ids."""
    sid = ts.scope_id(scope, m)
    r = ts.engram(m).assert_relation(
        subject, kind, object, sid, subject_kind=subject_kind, object_kind=object_kind
    )
    return Outcome(r, updated=[("Entity", r["subject_id"]), ("Entity", r["object_id"])])
