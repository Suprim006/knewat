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
    suspect_facts: int = Field(
        default=0,
        description="Active facts that are suspect now: verify_state = 'suspect' or a review date that has passed.",
    )
    dormant_facts: int = Field(default=0, description="Facts a memory_sweep moved to status 'dormant'.")
    pinned_facts: int = Field(default=0, description="Facts pinned with pin_fact.")
    changes: int = Field(default=0, description="Change nodes (code changes reported to mark_changed).")
    code_anchors: int = Field(
        default=0, description="CodeAnchor nodes (files and Python symbols facts are anchored to)."
    )


class GraphNode(BaseModel):
    id: str
    label: str
    props: dict[str, PropValue] = Field(
        description="Whitelisted display properties; nulls dropped; embeddings never sent. Fact nodes always carry "
        "verify_state ('verified' | 'suspect'), suspect_since (epoch ms, 0 = never), surprise (0..1), pinned and status "
        "(active | superseded | dormant | forgotten | quarantined), with defaults for facts written before P7; and, "
        "unless PLEXUS_FORGETTING=off, activation (float, omitted when -inf) and protected (bool)."
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
    suspected_by: list[str] = Field(
        default_factory=list, description="Change ids that made this fact suspect (P7)."
    )
    verified_by: list[str] = Field(default_factory=list, description="Agents that re-checked this fact (P7).")


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


class VerifyChange(BaseModel):
    change_id: str
    commit: str
    at: int
    paths: list[str]


class VerifyRow(BaseModel):
    """A fact to re-check (``Staleness.facts_to_verify``), with its activation when forgetting is on."""

    fact_id: str
    entity: str
    predicate: str
    value: str
    scope_id: str
    verify_state: str = Field(
        description="'suspect' (code changed) or 'verified' (only a review date passed)."
    )
    suspect_since: int
    verify_after: int
    reason: str
    decisions_count: int = Field(description="Decisions (not flagged) that rest on the fact.")
    anchors: list[str] = Field(
        description="path#symbol of the anchors, then the uris of the Sources it derives from."
    )
    change: VerifyChange | None = None
    activation: float | None = Field(
        default=None, description="Absent (null) when forgetting is off or the fact has no usable events."
    )
    protected: bool | None = Field(default=None, description="Absent (null) when forgetting is off.")


class VerifyQueueResponse(BaseModel):
    rows: list[VerifyRow] = Field(
        description="Ordered by decisions_count DESC, activation DESC, suspect_since ASC (activation only when forgetting is on)."
    )


class DocChange(BaseModel):
    change_id: str
    commit: str
    at: int
    paths: list[str]
    anchor: str


class DocRow(BaseModel):
    source_id: str
    uri: str
    title: str
    latest: int
    changes: list[DocChange]


class DocsToUpdateResponse(BaseModel):
    docs: list[DocRow]


class MemoryStrengthResponse(BaseModel):
    """``Activation.strength``: why a fact ranks where it does. Reading it does not count as a use."""

    fact_id: str
    status: str
    activation: float | None = Field(description="null when the fact has no usable events (A = -inf).")
    a0: float = Field(
        description="The neutral activation: the multiplier is half way between floor and 1 there."
    )
    multiplier: float
    floor: float
    decay: float
    protected: bool
    protect_reasons: list[str]
    pinned: bool
    surprise: float
    created_at: int
    verify_state: str
    suspect_since: int
    counts: dict[str, int] = Field(
        description="Events considered, by kind (create, reassert, decision, handoff, use, recall, verified)."
    )
    events_considered: int
    last_use: int | None = None
    last_recall: int | None = None
    explanation: str
    forgetting: bool = Field(
        description="False when PLEXUS_FORGETTING=off: recall ignores activation (this is still computed)."
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
    RecallResponse,
    VerifyQueueResponse,
    DocsToUpdateResponse,
    MemoryStrengthResponse,
    QueryText,
    ErrorBody,
)
