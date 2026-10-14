"""Pydantic response models for the View API (exported to docs/view-api.schema.json).

Shapes are what ``plexus-view`` consumes; field names are final. Times are epoch milliseconds.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

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
    created: list[NodeRef]
    updated: list[NodeRef]


class FlowResponse(BaseModel):
    events: list[ToolCallEvent]
    last_at: int = Field(
        description="Largest `at` returned (or `after` when empty); pass it as the next `after`."
    )


class StepAgent(BaseModel):
    agent_id: str
    step_n: int = Field(description="This agent's latest step <= the requested n.")
    step_at: int
    read: list[dict[str, Any]] = Field(
        description="Facts read, valid at step_at: id, predicate, value, status, valid_from, valid_to."
    )
    wrote: list[NodeRef]


class StepResponse(BaseModel):
    n: int
    agents: list[StepAgent]


class WhyResponse(BaseModel):
    id: str
    result: Any = Field(
        description="Lineage `why` result: paths plus flat nodes/edges (shape owned by plexus.lineage)."
    )


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
    QueryText,
    ErrorBody,
)
