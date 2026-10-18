"""Relay MCP tools: agents, a task DAG with leases, handoffs, artifacts and decisions.

Same shape as :mod:`knewat.mcp.tools_engram`: every tool takes ``agent_id`` and an optional ``step``; the tenant is
bound to the connection; each tool body is one service call that :meth:`Runtime.call` times, audits and attaches to
the agent's ``Step``.
"""

from typing import Annotated

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from knewat.mcp.limits import (
    MAX_ID,
    MAX_INT,
    MAX_LIST,
    AgentId,
    IdStr,
    LeaseMs,
    Name,
    Short,
    Step,
    StrictModel,
    TextReq,
    Title,
    Value,
    Version,
)
from knewat.mcp.runtime import MeteredClient, Outcome, TenantState
from knewat.mcp.toolkit import ToolTable
from knewat.relay.service import MAX_BLOCKED_DEPTH

MAX_TASKS = 200

RELAY_TOOLS = ToolTable()
tool = RELAY_TOOLS


class TaskSpec(StrictModel):
    title: Title = Field(description="Short imperative task title.")
    id: Annotated[str | None, Field(min_length=1, max_length=MAX_ID)] = Field(
        default=None, description="Optional stable id; generated if omitted."
    )
    priority: Annotated[int, Field(ge=-MAX_INT, le=MAX_INT)] = Field(
        default=0, description="Higher is claimed first."
    )
    depends_on: Annotated[list[IdStr], Field(max_length=MAX_LIST)] = Field(
        default_factory=list,
        description="Ids of tasks that must be 'done' first (in this batch or already existing).",
    )


class ArtifactSpec(StrictModel):
    kind: Name = Field(description="e.g. 'file', 'url', 'report'.")
    uri: Short = Field(description="Where the artifact lives (path or URL).")
    id: Annotated[str | None, Field(min_length=1, max_length=MAX_ID)] = Field(
        default=None, description="Optional id; generated if omitted."
    )
    hash: Name = Field(default="", description="Optional content hash, so others can verify it.")
    summary: Value = Field(default="", description="One line describing the artifact.")


def _dump(specs: list[ArtifactSpec]) -> list[dict]:
    return [s.model_dump(exclude_none=True) for s in specs]


# ---------------------------------------------------------------- agents and tasks
@tool
def register_agent(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    name: Annotated[Name, Field(description="Display name (defaults to agent_id).")] = "",
    role: Annotated[Name, Field(description="e.g. 'planner', 'researcher', 'builder'.")] = "",
    harness: Annotated[Name, Field(description="e.g. 'claude-code'.")] = "",
    step: Step = None,
) -> Outcome:
    """Register (or refresh) yourself as a team member so you can claim tasks and receive handoffs. Needed
    before claim_next_task unless you already called start_session."""
    r = ts.relay(m).register_agent(agent_id, name or agent_id, role, harness)
    return Outcome({"agent": r}, updated=[("Agent", agent_id)])


@tool
def create_tasks(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    tasks: Annotated[
        list[TaskSpec],
        Field(
            description=f"The task graph to create (max {MAX_TASKS} tasks).",
            min_length=1,
            max_length=MAX_TASKS,
        ),
    ],
    step: Step = None,
) -> Outcome:
    """Create a batch of tasks with dependencies (a DAG) in one atomic step: all are created or none. A task
    becomes claimable once everything in its depends_on is done. Returns the task ids in input order."""
    ids = ts.relay(m).create_tasks([t.model_dump(exclude_none=True) for t in tasks], step_id=m.step_id)
    return Outcome({"task_ids": ids}, created=[("Task", i) for i in ids], linked=ids if m.step_id else ())


@tool
def claim_next_task(
    ts: TenantState, m: MeteredClient, agent_id: AgentId, lease_ms: LeaseMs = 60_000, step: Step = None
) -> Outcome:
    """Atomically claim the highest-priority task that is ready (all dependencies done). No two agents can win
    the same task. Returns {task: null} when nothing is ready. Keep the 'version' for complete_task/fail_task and
    call heartbeat while working."""
    t = ts.relay(m).claim_next_task(agent_id, lease_ms, step_id=m.step_id)
    if t is None:
        return Outcome({"task": None})
    return Outcome({"task": t}, updated=[("Task", t["id"])], linked=[t["id"]] if m.step_id else ())


@tool
def heartbeat(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    task_id: Annotated[IdStr, Field(description="The task you claimed.")],
    lease_ms: LeaseMs = 60_000,
    step: Step = None,
) -> Outcome:
    """Extend your lease on a claimed task. Returns {alive: false} if you no longer hold it (it was taken over)."""
    ok = ts.relay(m).heartbeat(agent_id, task_id, lease_ms)
    return Outcome({"alive": ok, "task_id": task_id}, updated=[("Task", task_id)] if ok else [])


@tool
def complete_task(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    task_id: Annotated[IdStr, Field(description="The task you claimed.")],
    expected_version: Annotated[Version, Field(description="The 'version' returned by claim_next_task.")],
    artifacts: Annotated[
        list[ArtifactSpec],
        Field(description="What you produced (files, URLs, reports).", max_length=MAX_LIST),
    ] = [],  # noqa: B006
    step: Step = None,
) -> Outcome:
    """Mark a claimed task done and attach the artifacts you produced. Fails with a conflict if you no longer
    hold the task at that version (someone else reclaimed it). Completing unblocks dependent tasks."""
    r = ts.relay(m).complete_task(agent_id, task_id, expected_version, _dump(artifacts), step_id=m.step_id)
    return Outcome(
        r,
        created=[("Artifact", a) for a in r["artifact_ids"]],
        updated=[("Task", task_id)],
        linked=[task_id] if m.step_id else (),
    )


@tool
def fail_task(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    task_id: Annotated[IdStr, Field(description="The task you claimed.")],
    expected_version: Annotated[Version, Field(description="The 'version' returned by claim_next_task.")],
    reason: Annotated[Value, Field(description="Why it failed.")] = "",
    artifacts: Annotated[
        list[ArtifactSpec], Field(description="Any partial output worth keeping.", max_length=MAX_LIST)
    ] = [],  # noqa: B006
    step: Step = None,
) -> Outcome:
    """Mark a claimed task failed. Tasks that depend on it stay blocked (see blocked_by_failure)."""
    r = ts.relay(m).fail_task(
        agent_id, task_id, expected_version, _dump(artifacts), reason, step_id=m.step_id
    )
    return Outcome(
        r,
        created=[("Artifact", a) for a in r["artifact_ids"]],
        updated=[("Task", task_id)],
        linked=[task_id] if m.step_id else (),
    )


@tool
def reopen_task(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    task_id: Annotated[IdStr, Field(description="A task that is currently 'failed'.")],
    step: Step = None,
) -> Outcome:
    """Retry a failed task: it becomes 'open' again so it can be claimed (by anyone, including you). Fails
    if the task is not failed. Tasks that depend on it stay blocked until it is done again. Returns the new
    status and version."""
    r = ts.relay(m).reopen_task(agent_id, task_id, step_id=m.step_id)
    return Outcome({"task": r}, updated=[("Task", task_id)], linked=[task_id] if m.step_id else ())


# ---------------------------------------------------------------- handoffs, artifacts, decisions
@tool
def handoff(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    to_agent: Annotated[IdStr, Field(description="Agent id receiving the work (must be registered).")],
    task_id: Annotated[IdStr, Field(description="The task this handoff is about.")],
    note: Annotated[TextReq, Field(description="What the next agent needs to know.")],
    artifact_ids: Annotated[
        list[IdStr], Field(description="Artifacts you hand over.", max_length=MAX_LIST)
    ] = [],  # noqa: B006
    fact_ids: Annotated[
        list[IdStr], Field(description="Facts (evidence) you hand over.", max_length=MAX_LIST)
    ] = [],  # noqa: B006
    step: Step = None,
) -> Outcome:
    """Hand work to another agent with a note plus the artifacts and facts it should rely on. Everything
    referenced must exist, otherwise nothing is written."""
    hid = ts.relay(m).handoff(agent_id, to_agent, task_id, note, artifact_ids, fact_ids, step_id=m.step_id)
    return Outcome(
        {"handoff_id": hid},
        created=[("Handoff", hid)],
        read_ids=fact_ids,
        linked=[hid] if m.step_id else (),
    )


@tool
def verify_artifact(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    artifact_id: Annotated[IdStr, Field(description="Artifact to verify, e.g. after checking it yourself.")],
    step: Step = None,
) -> Outcome:
    """Record that you independently checked an artifact. 'independent' is false if you produced it yourself."""
    r = ts.relay(m).verify_artifact(agent_id, artifact_id)
    return Outcome(r, updated=[("Artifact", artifact_id)])


@tool
def record_decision(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    task_id: Annotated[IdStr, Field(description="The task the decision is for.")],
    text: Annotated[TextReq, Field(description="The decision and its reason, in one or two sentences.")],
    based_on_fact_ids: Annotated[
        list[IdStr],
        Field(
            description="Facts (from recall) this decision rests on, so it can be explained later.",
            max_length=MAX_LIST,
        ),
    ] = [],  # noqa: B006
    step: Step = None,
) -> Outcome:
    """Log a decision you made and the facts it is based on. Later anyone can ask WHY it was made. All fact ids
    must exist or nothing is written."""
    did = ts.relay(m).record_decision(agent_id, task_id, text, based_on_fact_ids, step_id=m.step_id)
    return Outcome(
        {"decision_id": did},
        created=[("Decision", did)],
        read_ids=based_on_fact_ids,
        linked=[did] if m.step_id else (),
    )


# ---------------------------------------------------------------- reads
@tool(kind="read")
def ready_tasks(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    limit: Annotated[int, Field(ge=1, le=200)] = 20,
    step: Step = None,
) -> Outcome:
    """List tasks that could be claimed right now (dependencies done), best first, without claiming any."""
    rows = ts.relay(m).ready_tasks(limit=limit)
    return Outcome({"tasks": rows, "count": len(rows)})


@tool(kind="read")
def task_status(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    task_id: Annotated[IdStr, Field(description="Task id.")],
    step: Step = None,
) -> Outcome:
    """Show one task: status, owner, lease, version, and the status of each dependency."""
    st = ts.relay(m).task_status(task_id)
    if st is None:
        raise ToolError(f"task_status: unknown task id: {task_id}")
    return Outcome({"task": st})


@tool(kind="read")
def blocked_by_failure(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    task_id: Annotated[IdStr, Field(description="The failed (or stuck) task.")],
    depth: Annotated[
        int,
        Field(
            description=f"How many dependency hops to follow (1..{MAX_BLOCKED_DEPTH}, default {MAX_BLOCKED_DEPTH}).",
            ge=1,
            le=MAX_BLOCKED_DEPTH,
        ),
    ] = MAX_BLOCKED_DEPTH,
    step: Step = None,
) -> Outcome:
    """List every unfinished task that transitively depends on this one (what a failure is blocking)."""
    if ts.relay(m).task_status(task_id) is None:
        raise ToolError(f"blocked_by_failure: unknown task id: {task_id}")
    ids = ts.relay(m).blocked_by_failure(task_id, depth=depth)
    return Outcome({"blocked": ids, "count": len(ids)})
