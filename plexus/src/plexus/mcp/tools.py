"""Engram + Relay MCP tools.

Every tool takes ``agent_id`` (who is acting) and an optional ``step`` (the agent's own step counter, used by the
time machine). The tenant is NOT an argument: it is bound to the connection (see ``plexus.mcp.runtime``).
Each tool body is one service call; :meth:`Runtime.call` times it, records a ``ToolCall`` and (when Lineage is
installed) attaches the call to the agent's ``Step``: ``WROTE`` for what it created or updated, ``READ`` for the
facts it looked at (``Outcome.read_ids`` / ``Outcome.assert_result`` / ``Outcome.after``).
"""

from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from plexus.mcp.runtime import MeteredClient, Outcome, Runtime, TenantState

AgentId = Annotated[
    str,
    Field(
        description="Your stable agent id, e.g. 'planner' or 'builder-2'. Identifies who is acting.",
        min_length=1,
    ),
]
Step = Annotated[
    int | None,
    Field(
        description="Optional: your own step counter (1, 2, 3...); calls with the same step share one step. "
        "If omitted, every call becomes the next step automatically. Never go backwards."
    ),
]
ScopeArg = Annotated[
    str,
    Field(
        description="Memory scope: 'global' (shared by everyone, default), 'project:<name>' or 'user:<name>' "
        "(project/user scopes also see 'global'), or a scope id."
    ),
]
LeaseMs = Annotated[
    int,
    Field(
        description="Lease length in milliseconds. Heartbeat before it runs out or others may take the task.",
        gt=0,
    ),
]


class TaskSpec(BaseModel):
    title: str = Field(description="Short imperative task title.")
    id: str | None = Field(default=None, description="Optional stable id; generated if omitted.")
    priority: int = Field(default=0, description="Higher is claimed first.")
    depends_on: list[str] = Field(
        default_factory=list,
        description="Ids of tasks that must be 'done' first (in this batch or already existing).",
    )


class ArtifactSpec(BaseModel):
    kind: str = Field(description="e.g. 'file', 'url', 'report'.")
    uri: str = Field(description="Where the artifact lives (path or URL).")
    id: str | None = Field(default=None, description="Optional id; generated if omitted.")
    hash: str = Field(default="", description="Optional content hash, so others can verify it.")
    summary: str = Field(default="", description="One line describing the artifact.")


def _fact_ref(fid: str) -> tuple[str, str]:
    return ("Fact", fid)


def register_engram_relay(mcp: MCPServer, rt: Runtime) -> list[str]:
    """Register the Engram and Relay tools on ``mcp``; returns their names."""
    names: list[str] = []

    def tool(fn):
        names.append(fn.__name__)
        return mcp.tool()(fn)

    # ---------------------------------------------------------------- Engram: sessions and episodes
    @tool
    async def start_session(
        agent_id: AgentId,
        ctx: Context,
        agent_role: Annotated[
            str, Field(description="Your role, e.g. 'planner', 'researcher', 'builder'.")
        ] = "",
        harness: Annotated[str, Field(description="What runs you, e.g. 'claude-code'.")] = "",
        step: Step = None,
    ) -> dict[str, Any]:
        """Begin a memory session. Call this FIRST in every run. It registers you as an agent and returns a
        session_id that you pass to remember_episode. Safe to call again in a later run: memory persists across
        sessions."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            sid = ts.engram(m).start_session(agent_id, agent_role, harness=harness)
            return Outcome(
                {"session_id": sid, "agent_id": agent_id},
                created=[("Session", sid)],
                updated=[("Agent", agent_id)],
            )

        return await rt.call(ctx.headers, "start_session", agent_id, step, work)

    @tool
    async def remember_episode(
        agent_id: AgentId,
        session_id: Annotated[str, Field(description="The session_id returned by start_session.")],
        text: Annotated[
            str, Field(description="What happened / was said, in your own words. Keep it factual.")
        ],
        ctx: Context,
        role: Annotated[
            str, Field(description="Who is speaking: 'user', 'assistant', 'tool' or 'note'.")
        ] = "note",
        step: Step = None,
    ) -> dict[str, Any]:
        """Append an episode (one event of the conversation or work log) to your session's timeline. Use it for
        raw history ("user asked X", "I tried Y and it failed"). For durable knowledge use assert_fact instead."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            eid = ts.engram(m).remember_episode(session_id, role, text, step)
            return Outcome(
                {"episode_id": eid, "session_id": session_id},
                created=[("Episode", eid)],
                updated=[("Session", session_id)],
            )

        return await rt.call(ctx.headers, "remember_episode", agent_id, step, work)

    # ---------------------------------------------------------------- Engram: facts
    @tool
    async def assert_fact(
        agent_id: AgentId,
        subject: Annotated[str, Field(description="What the fact is about, e.g. 'API' or 'Acme Notes API'.")],
        predicate: Annotated[str, Field(description="The attribute, e.g. 'version', 'database', 'owner'.")],
        value: Annotated[str, Field(description="The value, e.g. 'v1'.")],
        ctx: Context,
        scope: ScopeArg = "global",
        source_id: Annotated[
            str | None,
            Field(
                description="Optional Source id (from add_source) this fact comes from. The fact is linked to "
                "it, so it can be explained with why() and removed with forget_source / quarantine_source."
            ),
        ] = None,
        episode_id: Annotated[
            str | None, Field(description="Optional episode_id that evidences this fact.")
        ] = None,
        confidence: Annotated[float, Field(ge=0.0, le=1.0, description="How sure you are, 0..1.")] = 1.0,
        supersede: Annotated[
            bool,
            Field(description="True to replace the current value even if another agent asserted it."),
        ] = False,
        subject_kind: Annotated[
            str, Field(description="Entity kind, e.g. 'thing', 'person', 'service'.")
        ] = "thing",
        step: Step = None,
    ) -> dict[str, Any]:
        """Store a durable fact (subject, predicate, value) in shared memory. A new value for the same
        subject+predicate closes the old one (your own earlier value is superseded; a different agent's value is
        reported in 'contradicts' unless supersede=true). Asserting the same value again is a no-op that returns
        'duplicate_of'. Returns fact_id, superseded[], duplicate_of, contradicts[]."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
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
            data = {**r, "scope_id": sid}
            created = [] if r["duplicate_of"] else [_fact_ref(r["fact_id"])]
            updated = [_fact_ref(f) for f in r["superseded"]]
            if r["duplicate_of"]:
                updated.append(_fact_ref(r["duplicate_of"]))
            return Outcome(data, created=created, updated=updated, assert_result=r)

        return await rt.call(ctx.headers, "assert_fact", agent_id, step, work)

    @tool
    async def recall(
        agent_id: AgentId,
        query: Annotated[str, Field(description="Natural-language question or topic, e.g. 'API version'.")],
        ctx: Context,
        scope: ScopeArg = "global",
        k: Annotated[int, Field(ge=1, le=50, description="Max number of facts to return.")] = 8,
        as_of: Annotated[
            int | None,
            Field(
                description="Epoch milliseconds: answer as the world was then (includes since-replaced values)."
            ),
        ] = None,
        budget_chars: Annotated[
            int, Field(ge=50, le=20000, description="Rough cap on total returned text.")
        ] = 2000,
        step: Step = None,
    ) -> dict[str, Any]:
        """Search shared memory for facts relevant to a question (semantic + graph expansion), best first. Use this
        before acting, to learn what the team already knows. Each hit has fact_id, text, value, validity window
        and a 'path' showing where it came from. Also returns recall_id: pass it to why_recalled to see why these
        facts came back, in this order."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            sid = ts.scope_id(scope, m)
            hits = ts.engram(m).recall(query, sid, k=k, as_of=as_of, budget_chars=budget_chars)
            for h in hits:
                h["score"] = round(h["score"], 4)

            def record(lin, step_id: str | None) -> dict[str, Any]:
                return {"recall_id": lin.record_recall(agent_id, step_id, query, sid, k, hits)}

            return Outcome({"facts": hits, "count": len(hits), "scope_id": sid}, after=record)

        return await rt.call(ctx.headers, "recall", agent_id, step, work)

    @tool
    async def fact_history(
        agent_id: AgentId,
        subject: Annotated[str, Field(description="Subject of the fact, e.g. 'API'.")],
        predicate: Annotated[str, Field(description="Attribute, e.g. 'version'.")],
        ctx: Context,
        scope: ScopeArg = "global",
        step: Step = None,
    ) -> dict[str, Any]:
        """List every value a (subject, predicate) has had in a scope, oldest first, with validity windows and who
        asserted each. Use it to see how a fact changed over time."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            rows = ts.engram(m).fact_history(subject, predicate, ts.scope_id(scope, m))
            return Outcome({"history": [dict(r) for r in rows], "count": len(rows)})

        return await rt.call(ctx.headers, "fact_history", agent_id, step, work)

    # ---------------------------------------------------------------- Engram: procedures
    @tool
    async def log_procedure_run(
        agent_id: AgentId,
        procedure_name: Annotated[
            str, Field(description="Name of the method you used, e.g. 'run-tests-then-fix'.")
        ],
        task_type: Annotated[str, Field(description="Kind of task it was applied to, e.g. 'bugfix'.")],
        success: Annotated[bool, Field(description="Did it work?")],
        ctx: Context,
        task_id: Annotated[str | None, Field(description="Optional Relay task id this run was for.")] = None,
        notes: Annotated[str, Field(description="What happened, one or two lines.")] = "",
        steps: Annotated[
            list[str] | None, Field(description="Optional ordered list of the procedure's steps.")
        ] = None,
        step: Step = None,
    ) -> dict[str, Any]:
        """Record that you applied a named procedure to a kind of task and whether it worked. Over time this builds
        success rates that best_procedure uses to recommend what to try."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            rid = ts.engram(m).log_procedure_run(
                procedure_name, task_type, agent_id, success, task_id, notes, steps=steps, step=step
            )
            return Outcome({"run_id": rid}, created=[("Run", rid)])

        return await rt.call(ctx.headers, "log_procedure_run", agent_id, step, work)

    @tool
    async def best_procedure(
        agent_id: AgentId,
        task_type: Annotated[str, Field(description="Kind of task, e.g. 'bugfix'.")],
        ctx: Context,
        min_runs: Annotated[
            int, Field(ge=1, description="Ignore procedures tried fewer times than this.")
        ] = 1,
        limit: Annotated[int, Field(ge=1, le=20)] = 5,
        step: Step = None,
    ) -> dict[str, Any]:
        """Ask which procedures have worked best for a kind of task (ranked by success rate, then number of runs)."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            rows = ts.engram(m).best_procedure(task_type, min_runs, limit)
            return Outcome({"procedures": [dict(r) for r in rows], "count": len(rows)})

        return await rt.call(ctx.headers, "best_procedure", agent_id, step, work)

    # ---------------------------------------------------------------- Relay: agents and tasks
    @tool
    async def register_agent(
        agent_id: AgentId,
        ctx: Context,
        name: Annotated[str, Field(description="Display name (defaults to agent_id).")] = "",
        role: Annotated[str, Field(description="e.g. 'planner', 'researcher', 'builder'.")] = "",
        harness: Annotated[str, Field(description="e.g. 'claude-code'.")] = "",
        step: Step = None,
    ) -> dict[str, Any]:
        """Register (or refresh) yourself as a team member so you can claim tasks and receive handoffs. Needed
        before claim_next_task unless you already called start_session."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            r = ts.relay(m).register_agent(agent_id, name or agent_id, role, harness)
            return Outcome({"agent": r}, updated=[("Agent", agent_id)])

        return await rt.call(ctx.headers, "register_agent", agent_id, step, work)

    @tool
    async def create_tasks(
        agent_id: AgentId,
        tasks: Annotated[
            list[TaskSpec], Field(description="The task graph to create (max 500 tasks).", min_length=1)
        ],
        ctx: Context,
        step: Step = None,
    ) -> dict[str, Any]:
        """Create a batch of tasks with dependencies (a DAG) in one atomic step: all are created or none. A task
        becomes claimable once everything in its depends_on is done. Returns the task ids in input order."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            ids = ts.relay(m).create_tasks([t.model_dump(exclude_none=True) for t in tasks])
            return Outcome({"task_ids": ids}, created=[("Task", i) for i in ids])

        return await rt.call(ctx.headers, "create_tasks", agent_id, step, work)

    @tool
    async def claim_next_task(
        agent_id: AgentId,
        ctx: Context,
        lease_ms: LeaseMs = 60_000,
        step: Step = None,
    ) -> dict[str, Any]:
        """Atomically claim the highest-priority task that is ready (all dependencies done). No two agents can win
        the same task. Returns {task: null} when nothing is ready. Keep the 'version' for complete_task/fail_task and
        call heartbeat while working."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            t = ts.relay(m).claim_next_task(agent_id, lease_ms)
            if t is None:
                return Outcome({"task": None})
            return Outcome({"task": t}, updated=[("Task", t["id"])])

        return await rt.call(ctx.headers, "claim_next_task", agent_id, step, work)

    @tool
    async def heartbeat(
        agent_id: AgentId,
        task_id: Annotated[str, Field(description="The task you claimed.")],
        ctx: Context,
        lease_ms: LeaseMs = 60_000,
        step: Step = None,
    ) -> dict[str, Any]:
        """Extend your lease on a claimed task. Returns {alive: false} if you no longer hold it (it was taken over)."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            ok = ts.relay(m).heartbeat(agent_id, task_id, lease_ms)
            return Outcome({"alive": ok, "task_id": task_id}, updated=[("Task", task_id)] if ok else [])

        return await rt.call(ctx.headers, "heartbeat", agent_id, step, work)

    @tool
    async def complete_task(
        agent_id: AgentId,
        task_id: Annotated[str, Field(description="The task you claimed.")],
        expected_version: Annotated[int, Field(description="The 'version' returned by claim_next_task.")],
        ctx: Context,
        artifacts: Annotated[
            list[ArtifactSpec], Field(description="What you produced (files, URLs, reports).")
        ] = [],  # noqa: B006
        step: Step = None,
    ) -> dict[str, Any]:
        """Mark a claimed task done and attach the artifacts you produced. Fails with a conflict if you no longer
        hold the task at that version (someone else reclaimed it). Completing unblocks dependent tasks."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            r = ts.relay(m).complete_task(
                agent_id, task_id, expected_version, [a.model_dump(exclude_none=True) for a in artifacts]
            )
            return Outcome(
                r, created=[("Artifact", a) for a in r["artifact_ids"]], updated=[("Task", task_id)]
            )

        return await rt.call(ctx.headers, "complete_task", agent_id, step, work)

    @tool
    async def fail_task(
        agent_id: AgentId,
        task_id: Annotated[str, Field(description="The task you claimed.")],
        expected_version: Annotated[int, Field(description="The 'version' returned by claim_next_task.")],
        ctx: Context,
        reason: Annotated[str, Field(description="Why it failed.")] = "",
        artifacts: Annotated[list[ArtifactSpec], Field(description="Any partial output worth keeping.")] = [],  # noqa: B006
        step: Step = None,
    ) -> dict[str, Any]:
        """Mark a claimed task failed. Tasks that depend on it stay blocked (see blocked_by_failure)."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            r = ts.relay(m).fail_task(
                agent_id,
                task_id,
                expected_version,
                [a.model_dump(exclude_none=True) for a in artifacts],
                reason,
            )
            return Outcome(
                r, created=[("Artifact", a) for a in r["artifact_ids"]], updated=[("Task", task_id)]
            )

        return await rt.call(ctx.headers, "fail_task", agent_id, step, work)

    @tool
    async def reopen_task(
        agent_id: AgentId,
        task_id: Annotated[str, Field(description="A task that is currently 'failed'.")],
        ctx: Context,
        step: Step = None,
    ) -> dict[str, Any]:
        """Retry a failed task: it becomes 'open' again so it can be claimed (by anyone, including you). Fails
        if the task is not failed. Tasks that depend on it stay blocked until it is done again. Returns the new
        status and version."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            r = ts.relay(m).reopen_task(agent_id, task_id)
            return Outcome({"task": r}, updated=[("Task", task_id)])

        return await rt.call(ctx.headers, "reopen_task", agent_id, step, work)

    @tool
    async def handoff(
        agent_id: AgentId,
        to_agent: Annotated[str, Field(description="Agent id receiving the work (must be registered).")],
        task_id: Annotated[str, Field(description="The task this handoff is about.")],
        note: Annotated[str, Field(description="What the next agent needs to know.")],
        ctx: Context,
        artifact_ids: Annotated[list[str], Field(description="Artifacts you hand over.")] = [],  # noqa: B006
        fact_ids: Annotated[list[str], Field(description="Facts (evidence) you hand over.")] = [],  # noqa: B006
        step: Step = None,
    ) -> dict[str, Any]:
        """Hand work to another agent with a note plus the artifacts and facts it should rely on. Everything
        referenced must exist, otherwise nothing is written."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            hid = ts.relay(m).handoff(agent_id, to_agent, task_id, note, artifact_ids, fact_ids)
            return Outcome({"handoff_id": hid}, created=[("Handoff", hid)], read_ids=fact_ids)

        return await rt.call(ctx.headers, "handoff", agent_id, step, work)

    @tool
    async def verify_artifact(
        agent_id: AgentId,
        artifact_id: Annotated[
            str, Field(description="Artifact to verify, e.g. after checking it yourself.")
        ],
        ctx: Context,
        step: Step = None,
    ) -> dict[str, Any]:
        """Record that you independently checked an artifact. 'independent' is false if you produced it yourself."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            r = ts.relay(m).verify_artifact(agent_id, artifact_id)
            return Outcome(r, updated=[("Artifact", artifact_id)])

        return await rt.call(ctx.headers, "verify_artifact", agent_id, step, work)

    @tool
    async def record_decision(
        agent_id: AgentId,
        task_id: Annotated[str, Field(description="The task the decision is for.")],
        text: Annotated[str, Field(description="The decision and its reason, in one or two sentences.")],
        ctx: Context,
        based_on_fact_ids: Annotated[
            list[str],
            Field(description="Facts (from recall) this decision rests on, so it can be explained later."),
        ] = [],  # noqa: B006
        step: Step = None,
    ) -> dict[str, Any]:
        """Log a decision you made and the facts it is based on. Later anyone can ask WHY it was made. All fact ids
        must exist or nothing is written."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            did = ts.relay(m).record_decision(agent_id, task_id, text, based_on_fact_ids)
            return Outcome({"decision_id": did}, created=[("Decision", did)], read_ids=based_on_fact_ids)

        return await rt.call(ctx.headers, "record_decision", agent_id, step, work)

    # ---------------------------------------------------------------- Relay: reads
    @tool
    async def ready_tasks(
        agent_id: AgentId,
        ctx: Context,
        limit: Annotated[int, Field(ge=1, le=200)] = 20,
        step: Step = None,
    ) -> dict[str, Any]:
        """List tasks that could be claimed right now (dependencies done), best first, without claiming any."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            rows = ts.relay(m).ready_tasks(limit=limit)
            return Outcome({"tasks": rows, "count": len(rows)})

        return await rt.call(ctx.headers, "ready_tasks", agent_id, step, work)

    @tool
    async def task_status(
        agent_id: AgentId,
        task_id: Annotated[str, Field(description="Task id.")],
        ctx: Context,
        step: Step = None,
    ) -> dict[str, Any]:
        """Show one task: status, owner, lease, version, and the status of each dependency."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            st = ts.relay(m).task_status(task_id)
            if st is None:
                raise ToolError(f"task_status: unknown task id: {task_id}")
            return Outcome({"task": st})

        return await rt.call(ctx.headers, "task_status", agent_id, step, work)

    @tool
    async def blocked_by_failure(
        agent_id: AgentId,
        task_id: Annotated[str, Field(description="The failed (or stuck) task.")],
        ctx: Context,
        step: Step = None,
    ) -> dict[str, Any]:
        """List every unfinished task that transitively depends on this one (what a failure is blocking)."""

        def work(ts: TenantState, m: MeteredClient) -> Outcome:
            ids = ts.relay(m).blocked_by_failure(task_id)
            return Outcome({"blocked": ids, "count": len(ids)})

        return await rt.call(ctx.headers, "blocked_by_failure", agent_id, step, work)

    return names
