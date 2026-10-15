"""Engram MCP tools: sessions and episodes, facts (assert / recall / history) and procedures.

Every tool takes ``agent_id`` (who is acting) and an optional ``step`` (the agent's own step counter, used by the
time machine). The tenant is NOT an argument: it is bound to the connection (see ``plexus.mcp.runtime``). Each
tool body is one service call; :meth:`Runtime.call` times it, records a ``ToolCall`` and (when Lineage is
installed) attaches the call to the agent's ``Step``: ``WROTE`` for what it created or updated, ``READ`` for the
facts it looked at (``Outcome.read_ids`` / ``Outcome.assert_result`` / ``Outcome.after``). The tool pattern
itself (work function -> published tool) lives in :mod:`plexus.mcp.toolkit`.
"""

from typing import Annotated, Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from plexus.mcp.limits import (
    MAX_INT,
    MAX_LIST,
    AgentId,
    EpochMs,
    IdStr,
    Name,
    NameReq,
    ScopeArg,
    Short,
    Step,
    TextReq,
    Value,
)
from plexus.mcp.runtime import MeteredClient, Outcome, TenantState
from plexus.mcp.toolkit import ToolTable

Role = Literal["user", "assistant", "tool", "note"]

ENGRAM_TOOLS = ToolTable()
tool = ENGRAM_TOOLS


def _fact_ref(fid: str) -> tuple[str, str]:
    return ("Fact", fid)


# ---------------------------------------------------------------- sessions and episodes
@tool
def start_session(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    agent_role: Annotated[
        Name, Field(description="Your role, e.g. 'planner', 'researcher', 'builder'.")
    ] = "",
    harness: Annotated[Name, Field(description="What runs you, e.g. 'claude-code'.")] = "",
    step: Step = None,
) -> Outcome:
    """Begin a memory session. Call this FIRST in every run. It registers you as an agent and returns a
    session_id that you pass to remember_episode. Safe to call again in a later run: memory persists across
    sessions."""
    sid = ts.engram(m).start_session(agent_id, agent_role, harness=harness)
    return Outcome(
        {"session_id": sid, "agent_id": agent_id}, created=[("Session", sid)], updated=[("Agent", agent_id)]
    )


@tool
def remember_episode(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    session_id: Annotated[IdStr, Field(description="The session_id returned by start_session.")],
    text: Annotated[
        TextReq, Field(description="What happened / was said, in your own words. Keep it factual.")
    ],
    role: Annotated[
        Role, Field(description="Who is speaking: 'user', 'assistant', 'tool' or 'note'.")
    ] = "note",
    step: Step = None,
) -> Outcome:
    """Append an episode (one event of the conversation or work log) to your session's timeline. Use it for
    raw history ("user asked X", "I tried Y and it failed"). For durable knowledge use assert_fact instead."""
    eid = ts.engram(m).remember_episode(session_id, role, text, step)
    return Outcome(
        {"episode_id": eid, "session_id": session_id},
        created=[("Episode", eid)],
        updated=[("Session", session_id)],
    )


# ---------------------------------------------------------------- facts
@tool
def assert_fact(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    subject: Annotated[NameReq, Field(description="What the fact is about, e.g. 'API' or 'Acme Notes API'.")],
    predicate: Annotated[NameReq, Field(description="The attribute, e.g. 'version', 'database', 'owner'.")],
    value: Annotated[Value, Field(description="The value, e.g. 'v1'.")],
    scope: ScopeArg = "global",
    source_id: Annotated[
        IdStr | None,
        Field(
            description="Optional Source id (from add_source) this fact comes from. The fact is linked to "
            "it, so it can be explained with why() and removed with forget_source / quarantine_source."
        ),
    ] = None,
    episode_id: Annotated[
        IdStr | None, Field(description="Optional episode_id that evidences this fact.")
    ] = None,
    confidence: Annotated[float, Field(ge=0.0, le=1.0, description="How sure you are, 0..1.")] = 1.0,
    supersede: Annotated[
        bool, Field(description="True to replace the current value even if another agent asserted it.")
    ] = False,
    subject_kind: Annotated[
        Name, Field(description="Entity kind, e.g. 'thing', 'person', 'service'.")
    ] = "thing",
    step: Step = None,
) -> Outcome:
    """Store a durable fact (subject, predicate, value) in shared memory. A new value for the same
    subject+predicate closes the old one (your own earlier value is superseded; a different agent's value is
    reported in 'contradicts' unless supersede=true). Asserting the same value again is a no-op that returns
    'duplicate_of'. Returns fact_id, superseded[], duplicate_of, contradicts[]."""
    sid = ts.scope_id(scope, m)
    r = ts.engram(m).assert_fact(
        subject,
        predicate,
        value,
        sid,
        agent_id,
        source_id=source_id,
        episode_id=episode_id,
        confidence=confidence,
        supersede=supersede,
        subject_kind=subject_kind,
        step=step,
    )
    created = [] if r["duplicate_of"] else [_fact_ref(r["fact_id"])]
    updated = [_fact_ref(f) for f in r["superseded"]]
    if r["duplicate_of"]:
        updated.append(_fact_ref(r["duplicate_of"]))
    return Outcome({**r, "scope_id": sid}, created=created, updated=updated, assert_result=r)


@tool
def recall(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    query: Annotated[Value, Field(description="Natural-language question or topic, e.g. 'API version'.")],
    scope: ScopeArg = "global",
    k: Annotated[int, Field(ge=1, le=50, description="Max number of facts to return.")] = 8,
    as_of: Annotated[
        EpochMs | None,
        Field(
            description="Epoch milliseconds: answer as the world was then (includes since-replaced values)."
        ),
    ] = None,
    budget_chars: Annotated[
        int, Field(ge=50, le=20000, description="Rough cap on total returned text.")
    ] = 2000,
    include_dormant: Annotated[
        bool,
        Field(description="True to also search facts a memory_sweep moved to 'dormant' (hidden by default)."),
    ] = False,
    forgetting: Annotated[
        bool | None,
        Field(
            description="False = rank by relevance only; True = also by how much a fact is used; "
            "null = the server default (on)."
        ),
    ] = None,
    step: Step = None,
) -> Outcome:
    """Search shared memory for facts relevant to a question (semantic + graph expansion), best first. Use this
    before acting, to learn what the team already knows. Each hit has fact_id, text, value, validity window
    and a 'path' showing where it came from. Facts that are used, decided on, or surprising rank a little
    higher; unused old facts rank a little lower but are never hidden. Hits also say whether a fact is
    'suspect' (its code or review date changed: verify before relying on it) and 'protected'. Also returns
    recall_id: pass it to why_recalled to see why these facts came back, in this order."""
    sid = ts.scope_id(scope, m, create=False)  # a read never creates a Scope
    if sid is None:
        return Outcome({"facts": [], "count": 0, "scope_id": None})
    hits = ts.engram(m).recall(
        query,
        sid,
        k=k,
        as_of=as_of,
        budget_chars=budget_chars,
        include_dormant=include_dormant,
        forgetting=forgetting,
    )
    for h in hits:
        h["score"] = round(h["score"], 4)
        if h["activation"] is not None:
            h["activation"] = round(h["activation"], 3)

    def record(lin, step_id: str | None) -> dict[str, Any]:
        return {"recall_id": lin.record_recall(agent_id, step_id, query, sid, k, hits)}

    return Outcome({"facts": hits, "count": len(hits), "scope_id": sid}, after=record)


@tool
def fact_history(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    subject: Annotated[NameReq, Field(description="Subject of the fact, e.g. 'API'.")],
    predicate: Annotated[NameReq, Field(description="Attribute, e.g. 'version'.")],
    scope: ScopeArg = "global",
    step: Step = None,
) -> Outcome:
    """List every value a (subject, predicate) has had in a scope, oldest first, with validity windows and who
    asserted each. Use it to see how a fact changed over time."""
    sid = ts.scope_id(scope, m, create=False)  # a read never creates a Scope
    if sid is None:
        return Outcome({"history": [], "count": 0})
    rows = ts.engram(m).fact_history(subject, predicate, sid)
    return Outcome({"history": [dict(r) for r in rows], "count": len(rows)})


# ---------------------------------------------------------------- procedures
@tool
def log_procedure_run(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    procedure_name: Annotated[
        NameReq, Field(description="Name of the method you used, e.g. 'run-tests-then-fix'.")
    ],
    task_type: Annotated[NameReq, Field(description="Kind of task it was applied to, e.g. 'bugfix'.")],
    success: Annotated[bool, Field(description="Did it work?")],
    task_id: Annotated[
        IdStr | None, Field(description="Optional Relay task id this run was for (must exist).")
    ] = None,
    notes: Annotated[Value, Field(description="What happened, one or two lines.")] = "",
    steps: Annotated[
        list[Short] | None,
        Field(description="Optional ordered list of the procedure's steps.", max_length=MAX_LIST),
    ] = None,
    step: Step = None,
) -> Outcome:
    """Record that you applied a named procedure to a kind of task and whether it worked. Over time this builds
    success rates that best_procedure uses to recommend what to try."""
    if task_id is not None and ts.relay(m).task_status(task_id) is None:
        raise ToolError(f"log_procedure_run: unknown task id: {task_id}")
    rid = ts.engram(m).log_procedure_run(
        procedure_name, task_type, agent_id, success, task_id, notes, steps=steps, step=step
    )
    return Outcome({"run_id": rid}, created=[("Run", rid)])


@tool
def best_procedure(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    task_type: Annotated[NameReq, Field(description="Kind of task, e.g. 'bugfix'.")],
    min_runs: Annotated[
        int, Field(ge=1, le=MAX_INT, description="Ignore procedures tried fewer times than this.")
    ] = 1,
    limit: Annotated[int, Field(ge=1, le=20)] = 5,
    step: Step = None,
) -> Outcome:
    """Ask which procedures have worked best for a kind of task (ranked by success rate, then number of runs)."""
    rows = ts.engram(m).best_procedure(task_type, min_runs, limit)
    return Outcome({"procedures": [dict(r) for r in rows], "count": len(rows)})
