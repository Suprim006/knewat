"""Deterministic, non-LLM agents that play the Acme Notes scenario through the real MCP tools.

The scripted agents talk to the Plexus MCP server over an in-memory MCP ``Client`` (the same server object the
stdio / HTTP transports serve), so every call writes a ``ToolCall`` and a Lineage ``Step`` exactly as for a real
agent. Each call carries the *global* step number as its ``step`` argument, so the time machine's "step N" means
the same moment for every agent. The same scenario + fault script always builds the same graph (ids differ).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from mcp import Client
from plexus.demo.engine import BUILDER, AgentKilled, Driver, Turn, World
from plexus.demo.engine import run as run_engine
from plexus.demo.scenario import OPEN_LEASE_MS, FaultScript, load_scenario
from plexus.embed import Embedder
from plexus.graph.client import GraphClient
from plexus.mcp.runtime import Runtime
from plexus.mcp.server import build_server


class ToolFailed(RuntimeError):
    pass


class Caller:
    """One agent's handle on the MCP client: counts the global step, applies the kill fault, parses results."""

    def __init__(self, w: World, client: Client, agent: str):
        self.w, self.client, self.agent = w, client, agent

    async def __call__(self, tool: str, **args: Any) -> dict[str, Any]:
        w = self.w
        if w.should_kill(self.agent):
            task = w.holds.pop(self.agent)
            raise AgentKilled(self.agent, task)
        await w.pace()
        step = w.count_call(self.agent, tool)
        res = await self.client.call_tool(tool, {"agent_id": self.agent, "step": step, **args})
        text = res.content[0].text if res.content else ""
        if res.is_error:
            raise ToolFailed(f"{tool} (agent {self.agent}, step {step}): {text}")
        data = json.loads(text)
        if tool == "claim_next_task" and data.get("task"):
            w.holds[self.agent] = data["task"]["id"]
        elif tool in ("complete_task", "fail_task"):
            w.holds.pop(self.agent, None)
        return data


class ScriptedDriver:
    """Plays turns with fixed per-task handlers. Keeps ids (sessions, sources, facts, artifacts) between turns."""

    def __init__(self, client: Client):
        self.client = client
        self.sessions: dict[str, str] = {}
        self.sources: dict[str, str] = {}  # source stem -> source_id
        self.facts: dict[str, str] = {}  # logical name -> current fact id
        self.artifacts: dict[str, str] = {}  # task id -> artifact id
        self.last_recall: dict[str, str] = {}  # agent -> recall_id
        self._callers: dict[str, Caller] = {}

    def caller(self, w: World, agent: str) -> Caller:
        if agent not in self._callers:
            self._callers[agent] = Caller(w, self.client, agent)
        return self._callers[agent]

    # -- shared steps ----------------------------------------------------------------------------------------
    async def ensure_session(self, a: Caller) -> str:
        if a.agent not in self.sessions:
            r = await a("start_session", agent_role=a.agent, harness="scripted")
            self.sessions[a.agent] = r["session_id"]
        return self.sessions[a.agent]

    async def source(self, a: Caller, stem: str) -> str:
        doc = a.w.scenario.sources[stem]
        r = await a("add_source", title=doc.title, uri=doc.uri, text=doc.text, kind=doc.kind, trust=doc.trust)
        self.sources[stem] = r["source_id"]
        return r["source_id"]

    async def assert_(self, a: Caller, key: str, predicate: str, value: str, stem: str) -> dict[str, Any]:
        r = await a(
            "assert_fact",
            subject=a.w.scenario.subject,
            predicate=predicate,
            value=value,
            source_id=self.sources[stem],
        )
        self.facts[key] = r["fact_id"]
        return r

    async def recall(self, a: Caller, query: str) -> dict[str, Any]:
        r = await a("recall", query=query, k=5)
        self.last_recall[a.agent] = r["recall_id"]
        return r

    async def finish(self, a: Caller, t: dict[str, Any], uri: str, summary: str) -> str:
        r = await a(
            "complete_task",
            task_id=t["id"],
            expected_version=t["version"],
            artifacts=[{"kind": "file", "uri": uri, "summary": summary}],
        )
        self.artifacts[t["id"]] = r["artifact_ids"][0]
        return r["artifact_ids"][0]

    async def decide(self, a: Caller, task_id: str, text: str, facts: list[str]) -> str:
        r = await a("record_decision", task_id=task_id, text=text, based_on_fact_ids=facts)
        return r["decision_id"]

    async def hand(
        self, a: Caller, to: str, task_id: str, note: str, arts: list[str], facts: list[str]
    ) -> None:
        await a("handoff", to_agent=to, task_id=task_id, note=note, artifact_ids=arts, fact_ids=facts)

    # -- turns -----------------------------------------------------------------------------------------------
    async def run_turn(self, w: World, turn: Turn) -> None:
        a = self.caller(w, turn.agent)
        try:
            if turn.kind == "init":
                await self._init(w, a)
            elif turn.kind == "special":
                await self.ensure_session(a)
                await SPECIALS[turn.name](self, a)
            else:
                await self._task_turn(w, a, turn)
        except AgentKilled as k:
            self.sessions.pop(k.agent, None)  # a restarted agent opens a new session
            raise

    async def _init(self, w: World, a: Caller) -> None:
        await self.ensure_session(a)
        await a("create_tasks", tasks=[t.spec() for t in w.scenario.tasks])

    async def _task_turn(self, w: World, a: Caller, turn: Turn) -> None:
        await self.ensure_session(a)
        lease = w.faults.builder_lease_ms if a.agent == BUILDER else OPEN_LEASE_MS
        got = await a("claim_next_task", lease_ms=lease)
        t = got["task"]
        if t is None or t["id"] != turn.name:
            raise ToolFailed(f"{a.agent} expected to claim {turn.name}, got {t and t['id']}")
        await TASKS[t["id"]](self, a, t, turn)


# ------------------------------------------------------------------------------------------------ task handlers
async def t01(d: ScriptedDriver, a: Caller, t: dict, turn: Turn) -> None:
    await d.source(a, "01_product_brief")
    await d.source(a, "02_api_style_guide_v1")
    await d.assert_(
        a, "purpose", "purpose", "REST service to create, tag and search notes", "01_product_brief"
    )
    await d.assert_(a, "api_version", "api_version", "v1", "02_api_style_guide_v1")
    await d.finish(a, t, "artifacts/requirements.md", "Requirements: notes CRUD, tags, API version v1")


async def t02(d: ScriptedDriver, a: Caller, t: dict, turn: Turn) -> None:
    await d.decide(
        a,
        t["id"],
        "Build the Acme Notes API against v1 of the style guide (routes under /v1/).",
        [d.facts["api_version"]],
    )
    await a("complete_task", task_id=t["id"], expected_version=t["version"])


async def t03(d: ScriptedDriver, a: Caller, t: dict, turn: Turn) -> None:
    await d.recall(a, "API version")
    session = d.sessions[a.agent]
    if turn.reclaim_from:
        text = (
            f"Took over {t['id']} from {turn.reclaim_from}: its lease expired before it finished. "
            "Restarting the endpoint design from the recorded API version."
        )
    else:
        text = "Drafting the endpoint list: list/create/read/update/delete notes under /v1/notes."
    await a("remember_episode", session_id=session, text=text)
    art = await d.finish(a, t, "artifacts/openapi-draft.yaml", "Endpoint draft for /v1/notes (CRUD)")
    to = "builder" if a.agent != BUILDER else "planner"
    note = "Endpoint draft is ready." + (
        " Finished on the builder's behalf after it went down." if turn.reclaim_from else ""
    )
    await d.hand(a, to, t["id"], note, [art], [d.facts["api_version"]])


async def t04(d: ScriptedDriver, a: Caller, t: dict, turn: Turn) -> None:
    await d.source(a, "03_infra_note")
    await d.source(a, "04_security_note")
    await d.assert_(a, "database", "database", "PostgreSQL 16", "03_infra_note")
    await d.assert_(a, "auth_jwt", "auth_method", "JWT bearer tokens (RS256)", "04_security_note")
    await d.finish(
        a, t, "artifacts/constraints.md", "Infra and security constraints: PostgreSQL 16, JWT auth"
    )


async def t05(d: ScriptedDriver, a: Caller, t: dict, turn: Turn) -> None:
    await d.recall(a, "authentication")
    await d.source(a, "05_customer_request")
    r = await d.assert_(a, "auth_apikey", "auth_method", "API key in X-Api-Key header", "05_customer_request")
    a.w.event("auth_contradiction", agent=a.agent, new_fact=r["fact_id"], contradicts=r["contradicts"])
    await d.decide(
        a,
        t["id"],
        "Use JWT bearer tokens for user traffic (security requirement); offer API keys only later for service accounts.",
        [d.facts["auth_jwt"], d.facts["auth_apikey"]],
    )
    await a("complete_task", task_id=t["id"], expected_version=t["version"])


async def t06(d: ScriptedDriver, a: Caller, t: dict, turn: Turn) -> None:
    await d.recall(a, "database")
    await a(
        "remember_episode",
        session_id=d.sessions[a.agent],
        text="Schema: notes, tags and note_tags tables in PostgreSQL 16.",
    )
    await d.finish(a, t, "artifacts/schema.sql", "PostgreSQL 16 schema: notes, tags, note_tags")


async def t07(d: ScriptedDriver, a: Caller, t: dict, turn: Turn) -> None:
    await d.recall(a, "API version")
    await d.recall(a, "authentication")
    art = await d.finish(
        a, t, "artifacts/crud-spec.md", "CRUD spec for the current API version with JWT auth"
    )
    await d.hand(
        a,
        "planner",
        t["id"],
        "CRUD spec ready for review.",
        [art],
        [d.facts["api_version"], d.facts["auth_jwt"]],
    )


async def t08(d: ScriptedDriver, a: Caller, t: dict, turn: Turn) -> None:
    await d.recall(a, "API version")
    await d.finish(a, t, "artifacts/test-plan.md", "Test plan for the CRUD endpoints")


async def t09(d: ScriptedDriver, a: Caller, t: dict, turn: Turn) -> None:
    await d.recall(a, "API version")
    await a("verify_artifact", artifact_id=d.artifacts["t07-implement-crud-spec"])
    await d.decide(
        a,
        t["id"],
        "Spec approved: endpoints, schema and JWT auth are consistent.",
        [d.facts["api_version"], d.facts["auth_jwt"]],
    )
    await a("complete_task", task_id=t["id"], expected_version=t["version"])


async def t10(d: ScriptedDriver, a: Caller, t: dict, turn: Turn) -> None:
    await d.recall(a, "API version")
    await d.finish(a, t, "artifacts/docs.md", "API documentation")


async def t11(d: ScriptedDriver, a: Caller, t: dict, turn: Turn) -> None:
    art = await d.finish(a, t, "artifacts/release.tar", "Release bundle of the Acme Notes API")
    await d.hand(a, "planner", t["id"], "Release bundle is ready.", [art], [d.facts["api_version"]])


async def t12(d: ScriptedDriver, a: Caller, t: dict, turn: Turn) -> None:
    await d.recall(a, "API version")
    await a(
        "remember_episode",
        session_id=d.sessions[a.agent],
        text="Endpoint design moves from /v1/ to /v2/: page_token/page_size lists and problem+json errors.",
    )
    art = await d.finish(a, t, "artifacts/openapi-v2.yaml", "Endpoint design for /v2/notes")
    await d.hand(a, "planner", t["id"], "Updated for API v2.", [art], [d.facts["api_version"]])


TASKS: dict[str, Callable[[ScriptedDriver, Caller, dict, Turn], Awaitable[None]]] = {
    "t01-gather-requirements": t01,
    "t02-choose-api-version": t02,
    "t03-design-endpoints": t03,
    "t04-survey-infra-security": t04,
    "t05-choose-auth": t05,
    "t06-write-db-schema": t06,
    "t07-implement-crud-spec": t07,
    "t08-write-test-plan": t08,
    "t09-review-spec": t09,
    "t10-write-docs": t10,
    "t11-package-release": t11,
    "t12-update-endpoints-for-v2": t12,
}


# ------------------------------------------------------------------------------------------------ special turns
async def ingest_v2(d: ScriptedDriver, a: Caller) -> None:
    await d.source(a, "06_api_style_guide_v2")
    r = await d.assert_(a, "api_version", "api_version", "v2", "06_api_style_guide_v2")
    a.w.event("version_superseded", agent=a.agent, new_fact=r["fact_id"], superseded=r["superseded"])
    await a(
        "remember_episode",
        session_id=d.sessions[a.agent],
        text="Style guide v2 was published: API version v1 is withdrawn, routes move to /v2/.",
    )


async def adopt_v2(d: ScriptedDriver, a: Caller) -> None:
    await d.recall(a, "API version")
    await d.decide(
        a,
        "t02-choose-api-version",
        "Adopt style guide v2: the API version is now v2 (routes under /v2/).",
        [d.facts["api_version"]],
    )
    await a("create_tasks", tasks=[a.w.scenario.task("t12-update-endpoints-for-v2").spec()])


async def ingest_forum_post(d: ScriptedDriver, a: Caller) -> None:
    await d.source(a, "07_forum_post_unverified")
    r = await d.assert_(a, "database_poison", "database", "MongoDB 4", "07_forum_post_unverified")
    a.w.event("poison_fact", agent=a.agent, fact=r["fact_id"], contradicts=r["contradicts"])
    await d.decide(
        a,
        "t06-write-db-schema",
        "Evaluate MongoDB 4 as the database (forum post).",
        [d.facts["database_poison"]],
    )


async def quarantine_forum_post(d: ScriptedDriver, a: Caller) -> None:
    await d.recall(a, "database")
    sid = await d.source(a, "07_forum_post_unverified")
    r = await a("quarantine_source", source_id=sid)
    a.w.event("quarantine", source=sid, blast_radius=r["quarantined"])


SPECIALS: dict[str, Callable[[ScriptedDriver, Caller], Awaitable[None]]] = {
    "ingest-v2": ingest_v2,
    "adopt-v2": adopt_v2,
    "ingest-forum-post": ingest_forum_post,
    "quarantine-forum-post": quarantine_forum_post,
}


# ------------------------------------------------------------------------------------------------ entry point
async def run_scripted(
    tenant: str,
    client: GraphClient,
    *,
    embedder: Embedder | None = None,
    faults: FaultScript | None = None,
    pace_s: float = 0.0,
    on_call: Callable[[dict], None] | None = None,
) -> World:
    """Run the whole Acme Notes scenario with scripted agents on ``tenant``'s graph; returns the finished world."""
    w = World(load_scenario(), faults or FaultScript(), tenant, client, pace_s=pace_s, on_call=on_call)
    rt = Runtime(client=client, embedder=embedder, stdio_tenant=tenant)
    async with Client(build_server(rt)) as mcp:
        driver: Driver = ScriptedDriver(mcp)
        await run_engine(w, driver)
    return w
