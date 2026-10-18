"""A stdio MCP server that gives the file / SQLite / vector backends the Plexus tool surface (Layer 3).

BASELINE §0: "Tool API: identical MCP tool names and signatures in every arm. Only the tool descriptions differ".
This server registers, under the server name ``plexus``, the tools the Acme scenario's agents call, with the same
names and argument names as ``plexus.mcp.tools`` (``start_session``, ``remember_episode``, ``add_source``,
``assert_fact``, ``recall``, ``create_tasks``, ``claim_next_task``, ``heartbeat``, ``complete_task``, ``handoff``,
``record_decision``, ``verify_artifact``), each a thin call into a :class:`CoordinationBackend`. What the baseline
backends cannot do is not faked:

* the lineage tools (``why``, ``who_knew``, ``knew_at``, ``as_of``, ...) are not registered;
* ``start_session`` only registers the agent (the backends have no sessions); ``verify_artifact`` is acknowledged
  but not stored (the backends have no verification record);
* ``recall`` returns what the arm's own recall returns (grep-like for B0, BM25 for B1, cosine for B2).

Run: ``python -m plexus.crucible.l3.baseline_mcp --arm B0 --root DIR --tenant T`` (state lives on disk, so every
``claude -p`` process that starts this server sees the same team memory).
"""

import argparse
import functools
import logging
import sys
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from plexus.crucible.api import BackendSpec, CoordinationBackend, CrucibleError
from plexus.crucible.backends import open_backend

INSTRUCTIONS = (
    "Shared team memory and task coordination for a team of agents. Call start_session first. Use recall before "
    "acting and assert_fact to store durable knowledge; use create_tasks / claim_next_task / complete_task to "
    "coordinate, handoff to pass work on, and record_decision (with the fact ids it relies on). Every tool takes "
    "your agent_id."
)

AgentId = Annotated[str, Field(description="Your stable agent id, e.g. 'planner'.", min_length=1)]
Step = Annotated[int | None, Field(description="Optional: your own step counter (1, 2, 3...).")]


class TaskSpec(BaseModel):
    title: str = Field(description="Short imperative task title.")
    id: str | None = Field(default=None, description="Optional stable id; generated if omitted.")
    priority: int = Field(default=0, description="Higher is claimed first.")
    depends_on: list[str] = Field(default_factory=list, description="Ids of tasks that must be 'done' first.")


class ArtifactSpec(BaseModel):
    kind: str = Field(description="e.g. 'file', 'url', 'report'.")
    uri: str = Field(description="Where the artifact lives (path or URL).")
    id: str | None = Field(default=None, description="Optional id; generated if omitted.")
    hash: str = Field(default="", description="Optional content hash.")
    summary: str = Field(default="", description="One line describing the artifact.")


def _guard(fn):
    """Backend errors become tool errors (what the Plexus tools do), not crashes of the server."""

    @functools.wraps(fn)
    def wrapped(*a, **kw):
        try:
            return fn(*a, **kw)
        except (CrucibleError, ValueError) as exc:
            raise ToolError(f"{fn.__name__}: {exc}") from None

    return wrapped


def build_baseline_server(b: CoordinationBackend) -> MCPServer:
    mcp = MCPServer("plexus", instructions=INSTRUCTIONS, log_level="WARNING")

    def tool(fn):
        return mcp.tool()(_guard(fn))

    @tool
    def start_session(
        agent_id: AgentId,
        agent_role: Annotated[
            str, Field(description="Your role, e.g. 'planner', 'researcher', 'builder'.")
        ] = "",
        harness: Annotated[str, Field(description="What runs you, e.g. 'claude-code'.")] = "",
        step: Step = None,
    ) -> dict[str, Any]:
        """Begin a memory session. Call this FIRST in every run. It registers you as an agent and returns a
        session_id that you pass to remember_episode."""
        b.register_agent(agent_id, agent_role)
        return {"session_id": f"session-{agent_id}", "agent_id": agent_id}

    @tool
    def remember_episode(
        agent_id: AgentId,
        session_id: Annotated[str, Field(description="The session_id returned by start_session.")],
        text: Annotated[str, Field(description="What happened / was said, in your own words.")],
        role: Annotated[
            str, Field(description="Who is speaking: 'user', 'assistant', 'tool' or 'note'.")
        ] = "note",
        step: Step = None,
    ) -> dict[str, Any]:
        """Append an episode (one event of the work log) to the shared memory."""
        return {"episode_id": b.remember_episode(agent_id, text, step), "session_id": session_id}

    @tool
    def add_source(
        agent_id: AgentId,
        title: Annotated[str, Field(description="Short name of the source.")],
        uri: Annotated[str | None, Field(description="Where it lives (URL or path).")] = None,
        text: Annotated[str | None, Field(description="Optional excerpt or the pasted content.")] = None,
        kind: Annotated[str, Field(description="'doc', 'web', 'chat', 'note', 'tool'...")] = "doc",
        trust: Annotated[float, Field(ge=0.0, le=1.0, description="How far this source is trusted.")] = 1.0,
        step: Step = None,
    ) -> dict[str, Any]:
        """Register WHERE knowledge comes from and get a source_id to pass to assert_fact. The same uri
        returns the same source_id."""
        where = (uri or "").strip() or f"note:{title}"
        return {"source_id": b.add_source(where, kind, trust), "uri": where, "title": title}

    @tool
    def assert_fact(
        agent_id: AgentId,
        subject: Annotated[str, Field(description="What the fact is about, e.g. 'Acme Notes API'.")],
        predicate: Annotated[str, Field(description="The attribute, e.g. 'version', 'database'.")],
        value: Annotated[str, Field(description="The value, e.g. 'v1'.")],
        scope: Annotated[str, Field(description="'global', 'project:<name>' or 'user:<name>'.")] = "global",
        source_id: Annotated[str | None, Field(description="Optional Source id from add_source.")] = None,
        episode_id: Annotated[
            str | None, Field(description="Optional episode_id that evidences this fact.")
        ] = None,
        confidence: Annotated[float, Field(ge=0.0, le=1.0, description="How sure you are, 0..1.")] = 1.0,
        supersede: Annotated[
            bool, Field(description="True to replace the current value even if another agent asserted it.")
        ] = False,
        subject_kind: Annotated[str, Field(description="Entity kind, e.g. 'thing'.")] = "thing",
        step: Step = None,
    ) -> dict[str, Any]:
        """Store a durable fact (subject, predicate, value) in shared memory. A new value for the same
        subject+predicate closes the old one (your own earlier value is superseded; a different agent's value is
        reported in 'contradicts' unless supersede=true). Returns fact_id, superseded[], duplicate_of, contradicts[]."""
        return b.assert_fact(
            agent_id, subject, predicate, value, scope=scope, source_id=source_id, confidence=confidence,
            supersede=supersede,
        )  # fmt: skip

    @tool
    def recall(
        agent_id: AgentId,
        query: Annotated[str, Field(description="Natural-language question or topic, e.g. 'API version'.")],
        scope: Annotated[str, Field(description="Memory scope.")] = "global",
        k: Annotated[int, Field(ge=1, le=50, description="Max number of facts to return.")] = 8,
        as_of: Annotated[
            int | None, Field(description="Epoch milliseconds: answer as the world was then.")
        ] = None,
        budget_chars: Annotated[
            int, Field(ge=50, le=20000, description="Rough cap on total returned text.")
        ] = 2000,
        step: Step = None,
    ) -> dict[str, Any]:
        """Search shared memory for facts relevant to a question, best first. Each hit has fact_id, text, value."""
        hits = b.recall(agent_id, query, scope=scope, k=k, as_of=as_of)
        for h in hits:
            h["score"] = round(float(h["score"]), 4)
        return {"facts": hits, "count": len(hits), "recall_id": None}  # no why_recalled in this arm

    @tool
    def create_tasks(
        agent_id: AgentId,
        tasks: Annotated[
            list[TaskSpec], Field(description="The task graph to create (max 500 tasks).", min_length=1)
        ],
        step: Step = None,
    ) -> dict[str, Any]:
        """Create a batch of tasks with dependencies (a DAG) in one atomic step. A task becomes claimable once
        everything in its depends_on is done. Returns the task ids in input order."""
        return {"task_ids": b.create_tasks([t.model_dump(exclude_none=True) for t in tasks])}

    @tool
    def claim_next_task(
        agent_id: AgentId,
        lease_ms: Annotated[int, Field(description="Lease length in milliseconds.", gt=0)] = 60_000,
        step: Step = None,
    ) -> dict[str, Any]:
        """Atomically claim the highest-priority task that is ready (all dependencies done). Returns {task: null}
        when nothing is ready. Keep the 'version' for complete_task."""
        return {"task": b.claim_next_task(agent_id, lease_ms)}

    @tool
    def heartbeat(
        agent_id: AgentId,
        task_id: Annotated[str, Field(description="The task you claimed.")],
        lease_ms: Annotated[int, Field(description="Lease length in milliseconds.", gt=0)] = 60_000,
        step: Step = None,
    ) -> dict[str, Any]:
        """Extend your lease on a claimed task. Returns {alive: false} if you no longer hold it."""
        return {"alive": b.heartbeat(agent_id, task_id, lease_ms), "task_id": task_id}

    @tool
    def complete_task(
        agent_id: AgentId,
        task_id: Annotated[str, Field(description="The task you claimed.")],
        expected_version: Annotated[int, Field(description="The 'version' returned by claim_next_task.")],
        artifacts: Annotated[list[ArtifactSpec], Field(description="What you produced.")] = [],  # noqa: B006
        step: Step = None,
    ) -> dict[str, Any]:
        """Mark a claimed task done and attach the artifacts you produced. Fails with a conflict if you no longer
        hold the task at that version."""
        return b.complete_task(
            agent_id, task_id, expected_version, [a.model_dump(exclude_none=True) for a in artifacts]
        )

    @tool
    def handoff(
        agent_id: AgentId,
        to_agent: Annotated[str, Field(description="Agent id receiving the work.")],
        task_id: Annotated[str, Field(description="The task this handoff is about.")],
        note: Annotated[str, Field(description="What the next agent needs to know.")],
        artifact_ids: Annotated[list[str], Field(description="Artifacts you hand over.")] = [],  # noqa: B006
        fact_ids: Annotated[list[str], Field(description="Facts (evidence) you hand over.")] = [],  # noqa: B006
        step: Step = None,
    ) -> dict[str, Any]:
        """Hand work to another agent with a note plus the artifacts and facts it should rely on."""
        return {"handoff_id": b.handoff(agent_id, to_agent, task_id, note, artifact_ids, fact_ids)}

    @tool
    def record_decision(
        agent_id: AgentId,
        task_id: Annotated[str, Field(description="The task the decision is for.")],
        text: Annotated[str, Field(description="The decision and its reason, in one or two sentences.")],
        based_on_fact_ids: Annotated[list[str], Field(description="Facts this decision rests on.")] = [],  # noqa: B006
        step: Step = None,
    ) -> dict[str, Any]:
        """Log a decision you made and the facts it is based on."""
        return {"decision_id": b.record_decision(agent_id, task_id, text, based_on_fact_ids)}

    @tool
    def verify_artifact(
        agent_id: AgentId,
        artifact_id: Annotated[
            str, Field(description="Artifact to verify, e.g. after checking it yourself.")
        ],
        step: Step = None,
    ) -> dict[str, Any]:
        """Record that you independently checked an artifact."""
        return {"artifact_id": artifact_id, "verified_by": agent_id, "independent": True}

    return mcp


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="crucible-baseline-mcp", description=__doc__)
    ap.add_argument("--arm", choices=("B0", "B1", "B2"), required=True)
    ap.add_argument("--root", required=True, help="directory holding the arm's files / database")
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--embedder", default="fastembed")
    a = ap.parse_args(argv)
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    backend = open_backend(BackendSpec(arm=a.arm, tenant=a.tenant, root=a.root, embedder=a.embedder))
    build_baseline_server(backend).run("stdio")


if __name__ == "__main__":
    main()
