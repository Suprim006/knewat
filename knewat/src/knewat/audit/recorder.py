"""``record_tool_call``: write a ToolCall node plus IN_STEP / CREATED / UPDATED edges.

Backed by the named query ``audit/record_tool_call``.
"""

from __future__ import annotations

from collections.abc import Iterable

from plexus.common import new_id, now_ms
from plexus.graph.client import GraphClient

MAX_LINKS = 200  # CREATED/UPDATED edges per call (bounded write)
LINKABLE_LABELS = frozenset(
    {
        "Fact",
        "Episode",
        "Session",
        "Entity",
        "Scope",
        "Task",
        "Handoff",
        "Artifact",
        "Decision",
        "Run",
        "Agent",
        "Procedure",
        "Source",
        "Recall",
        "Change",
        "CodeAnchor",
    }
)

Ref = tuple[str, str]  # (label, id)


def _links(refs: Iterable[Ref], rel: str, budget: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for label, node_id in refs:
        if len(out) >= budget:
            break
        if label in LINKABLE_LABELS and node_id:
            out.append({"id": str(node_id), "label": label, "rel": rel})
    return out


def record_tool_call(
    client: GraphClient,
    graph: str,
    tool: str,
    agent_id: str,
    step_id: str | None,
    query_name: str,
    run_time_ms: float,
    created_ids: Iterable[Ref] = (),
    updated_ids: Iterable[Ref] = (),
    *,
    step: int | None = None,
    wrote: bool | None = None,
    now: int | None = None,
) -> str:
    """Record one tool call and return the ``ToolCall`` id.

    ``created_ids`` / ``updated_ids`` are ``(label, id)`` pairs (the label picks an index-backed lookup;
    unknown labels are dropped). ``wrote`` overrides the default (True when any link is written). At most
    :data:`MAX_LINKS` edges are written, CREATED first. ``step_id`` is a Lineage ``Step`` id; if it matches
    no node there is simply no ``IN_STEP`` edge.
    """
    created = _links(created_ids, "C", MAX_LINKS)
    updated = _links(updated_ids, "U", MAX_LINKS - len(created))
    call_id = new_id()
    t = now if now is not None else now_ms()
    rows = client.rw(
        graph,
        "audit/record_tool_call",
        {
            "id": call_id,
            "tool": tool,
            "agent_id": agent_id,
            "step_id": step_id or "",
            "step": -1 if step is None else step,
            "query_name": query_name,
            "run_time_ms": float(run_time_ms),
            "wrote": bool(created or updated) if wrote is None else wrote,
            "links": created + updated,
            "now": t,
        },
    )
    return rows[0]["id"]
