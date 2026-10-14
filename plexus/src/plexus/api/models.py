"""Pydantic response models for the View API (exported to docs/view-api.schema.json).

Shapes are what ``plexus-view`` consumes; field names are final. Times are epoch milliseconds.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

PropValue = str | int | float | bool


class TenantInfo(BaseModel):
    tenant: str = Field(description="Tenant id (graph name without the plexus_t_ prefix).")
    graph: str = Field(description="FalkorDB graph name.")


class TenantsResponse(BaseModel):
    tenants: list[TenantInfo]


class LabelInventory(BaseModel):
    label: str
    count: int
    keys: list[str] = Field(description="Property keys seen on a bounded sample of this label's nodes.")


class EdgeInventory(BaseModel):
    type: str
    count: int


class IndexInfo(BaseModel):
    label: str
    properties: list[str]
    types: dict[str, list[str]] = Field(description="Property -> index kinds (RANGE | FULLTEXT | VECTOR).")
    entity_type: str
    status: str


class InventoryResponse(BaseModel):
    tenant: str
    nodes_total: int
    edges_total: int
    labels: list[LabelInventory]
    edge_types: list[EdgeInventory]
    indexes: list[IndexInfo]


class GraphNode(BaseModel):
    id: str
    label: str
    props: dict[str, PropValue] = Field(
        description="Whitelisted display properties; nulls dropped; embeddings never sent."
    )


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool = Field(description="True if more nodes matched than `limit`.")
    limit: int


class NodeRef(BaseModel):
    id: str
    label: str


class ToolCallEvent(BaseModel):
    id: str
    tool: str
    at: int
    agent_id: str
    query_name: str
    run_time_ms: float
    wrote: bool
    step: int | None = Field(description="The agent's own step counter, if it sent one.")
    step_id: str | None = Field(description="Lineage Step node id, if the call is attached to one.")
    step_n: int | None = Field(
        default=None, description="That Step's number in its agent's chain (the step slider's value)."
    )
    created: list[NodeRef]
    updated: list[NodeRef]


class FlowResponse(BaseModel):
    events: list[ToolCallEvent]
    last_at: int = Field(
        description="Largest `at` returned (or `after` when empty); pass it as the next `after`."
    )


class StepFact(BaseModel):
    """A fact an agent had read by the step and that was still valid then (``Lineage.knew_at``)."""

    id: str
    entity: str | None = None
    predicate: str | None = None
    value: str | None = None
    status: str | None = None
    valid_from: int | None = None
    valid_to: int | None = None
    read_at_step: int | None = Field(default=None, description="The agent's first step that read it.")


class StepWrote(NodeRef):
    """A node the agent's steps wrote (Fact, Decision, Handoff or Task) up to the step."""

    summary: str | None = None
    step_n: int | None = Field(default=None, description="The agent's step that wrote it.")


class StepAgent(BaseModel):
    agent_id: str
    step_n: int = Field(description="This agent's latest step <= the requested n.")
    step_at: int
    read: list[StepFact] = Field(description="Facts read by then that were valid at step_at.")
    wrote: list[StepWrote]


class StepResponse(BaseModel):
    n: int
    agents: list[StepAgent]


class LineageNode(BaseModel):
    id: str
    label: str
    props: dict[str, Any] = Field(default_factory=dict)


class LineageEdge(BaseModel):
    """Stored direction from -[rel]-> to; props carries e.g. RETURNED's rank and score."""

    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    rel: str
    to: str
    props: dict[str, Any] | None = None


class WhyHop(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    rel: str
    to: str
    reverse: bool = Field(description="True when the edge is stored `to -> from`.")


class WhyFact(BaseModel):
    id: str
    props: dict[str, Any]
    asserted_by: list[str]
    sources: list[str]
    episodes: list[str]
    derived_from_facts: list[str]
    supersedes: list[str]
    superseded_by: list[str]
    contradicts: list[str]
    contradicted_by: list[str]
    written_by_steps: list[str]


class WhyResult(BaseModel):
    """``Lineage.why``: the facts a decision (or fact) rests on, their evidence, and the paths to it."""

    root: str
    kind: str = Field(description="Decision | Fact")
    facts: list[WhyFact]
    agents: list[str]
    sources: list[str]
    episodes: list[str]
    steps: list[str]
    paths: list[list[WhyHop]]
    nodes: list[LineageNode]
    edges: list[LineageEdge]
    truncated: bool


class WhyResponse(BaseModel):
    id: str
    result: WhyResult


class RecallInfo(BaseModel):
    id: str
    query: str
    at: int
    k: int
    scope_id: str
    agent_id: str
    step: dict[str, Any] | None = Field(default=None, description="{id, n, at} of the Step it ran in.")


class RecallHit(BaseModel):
    rank: int
    score: float
    fact_id: str
    props: dict[str, Any]
    entity: dict[str, Any] | None = None
    asserted_by: list[str]
    derived_from: list[dict[str, Any]]
    scope: dict[str, Any] | None = None


class WhyRecalledResult(BaseModel):
    """``Lineage.why_recalled``: a stored Recall with the facts it returned, in rank order."""

    recall: RecallInfo
    results: list[RecallHit]
    nodes: list[LineageNode]
    edges: list[LineageEdge]
    truncated: bool


class RecallResponse(BaseModel):
    id: str
    result: WhyRecalledResult


class QueryText(BaseModel):
    name: str
    mode: str
    purpose: str
    params: dict[str, str]
    returns: str
    text: str = Field(description="The full .cypher file text, header included.")


class ErrorBody(BaseModel):
    detail: str


# Models exported to docs/view-api.schema.json (one schema per response).
EXPORTED = (
    TenantsResponse,
    InventoryResponse,
    GraphResponse,
    FlowResponse,
    ToolCallEvent,
    StepResponse,
    WhyResponse,
    RecallResponse,
    QueryText,
    ErrorBody,
)
