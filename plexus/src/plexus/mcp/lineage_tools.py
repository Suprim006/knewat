"""Lineage MCP tools, registered only when ``plexus.lineage`` exists (P2-D merges separately).

``plexus.lineage.Lineage(client, graph)`` provides ``why``, ``why_recalled``, ``who_knew``, ``knew_at``, ``as_of``,
``create_source``, ``forget_source``, ``quarantine`` and ``release_quarantine``; a method that is missing is simply
not exposed as a tool. Step recording and READ/WROTE/Recall attachment for every call live in
``plexus.mcp.runtime``.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import logging
import sys
from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from plexus.mcp.limits import (
    MAX_INT,
    AgentId,
    EpochMs,
    IdStr,
    Name,
    NameReq,
    ScopeArg,
    Short,
    Step,
    Text,
    Title,
)
from plexus.mcp.runtime import MeteredClient, Outcome, Runtime, TenantState

log = logging.getLogger("plexus.mcp")


def lineage_available() -> bool:
    if sys.modules.get("plexus.lineage") is not None:
        return True
    try:
        return importlib.util.find_spec("plexus.lineage") is not None
    except (ImportError, ValueError):
        return False


def _lineage(ts: TenantState, m: MeteredClient):
    mod = importlib.import_module("plexus.lineage")
    return mod.Lineage(m, ts.graph)


def _jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, list | tuple | set):
        return [_jsonable(v) for v in x]
    return x if isinstance(x, str | int | float | bool | type(None)) else str(x)


def register_lineage(mcp: MCPServer, rt: Runtime) -> list[str]:
    """Register whichever Lineage tools the installed ``plexus.lineage`` provides. Returns their names."""
    if not lineage_available():
        return []
    mod = importlib.import_module("plexus.lineage")
    cls = getattr(mod, "Lineage", None)
    if cls is None:
        log.warning("plexus.lineage has no Lineage class; Lineage tools not registered")
        return []
    has = {
        n
        for n in (
            "why",
            "why_recalled",
            "who_knew",
            "knew_at",
            "as_of",
            "create_source",
            "forget_source",
            "quarantine",
            "release_quarantine",
        )
        if hasattr(cls, n)
    }
    names: list[str] = []

    def tool(fn):
        names.append(fn.__name__)
        return mcp.tool()(fn)

    if "why" in has:

        @tool
        async def why(
            agent_id: AgentId,
            node_id: Annotated[IdStr, Field(description="A decision id or a fact id.")],
            ctx: Context,
            step: Step = None,
        ) -> dict[str, Any]:
            """Explain WHY a decision was made (or where a fact comes from): the graph paths from a decision_id
            or fact_id to the facts it rests on, who asserted them, their sources, and the steps that wrote them."""

            def work(ts: TenantState, m: MeteredClient) -> Outcome:
                return Outcome({"why": _jsonable(_lineage(ts, m).why(node_id))})

            return await rt.call(ctx.headers, "why", agent_id, step, work)

    if "why_recalled" in has:

        @tool
        async def why_recalled(
            agent_id: AgentId,
            recall_id: Annotated[IdStr, Field(description="A recall id.")],
            ctx: Context,
            step: Step = None,
        ) -> dict[str, Any]:
            """Explain why a past recall returned the facts it did. The recall_id comes from the recall tool's
            result. Gives the query, each returned fact in rank order with its score, and where it came from."""

            def work(ts: TenantState, m: MeteredClient) -> Outcome:
                return Outcome({"why_recalled": _jsonable(_lineage(ts, m).why_recalled(recall_id))})

            return await rt.call(ctx.headers, "why_recalled", agent_id, step, work)

    if "who_knew" in has:

        @tool
        async def who_knew(
            agent_id: AgentId,
            fact_id: Annotated[IdStr, Field(description="A fact id.")],
            ctx: Context,
            step: Step = None,
        ) -> dict[str, Any]:
            """Which agents asserted, wrote or READ a fact, and at which step: who knew this, and since when."""

            def work(ts: TenantState, m: MeteredClient) -> Outcome:
                return Outcome({"who_knew": _jsonable(_lineage(ts, m).who_knew(fact_id))})

            return await rt.call(ctx.headers, "who_knew", agent_id, step, work)

    if "knew_at" in has:

        @tool
        async def knew_at(
            agent_id: AgentId,
            subject_agent: Annotated[IdStr, Field(description="The agent whose knowledge to reconstruct.")],
            step_n: Annotated[int, Field(description="The step number.", ge=0, le=MAX_INT)],
            ctx: Context,
            step: Step = None,
        ) -> dict[str, Any]:
            """Time machine: what a given agent knew at its step N (the facts it had read that were still valid
            then) and everything it had written by then."""

            def work(ts: TenantState, m: MeteredClient) -> Outcome:
                return Outcome({"knew_at": _jsonable(_lineage(ts, m).knew_at(subject_agent, step_n))})

            return await rt.call(ctx.headers, "knew_at", agent_id, step, work)

    if "as_of" in has:

        @tool
        async def as_of(
            agent_id: AgentId,
            subject: Annotated[NameReq, Field(description="Fact subject.")],
            predicate: Annotated[NameReq, Field(description="Fact attribute.")],
            t: Annotated[EpochMs, Field(description="Epoch milliseconds.")],
            ctx: Context,
            scope: ScopeArg = "global",
            step: Step = None,
        ) -> dict[str, Any]:
            """The value a (subject, predicate) had at time t (epoch ms), or null if it had none yet. Forgotten
            and quarantined facts never answer."""

            def work(ts: TenantState, m: MeteredClient) -> Outcome:
                sid = ts.scope_id(scope, m, create=False)  # a read never creates a Scope
                if sid is None:
                    return Outcome({"as_of": None})
                return Outcome({"as_of": _jsonable(_lineage(ts, m).as_of(subject, predicate, t, sid))})

            return await rt.call(ctx.headers, "as_of", agent_id, step, work)

    if "create_source" in has:

        @tool
        async def add_source(
            agent_id: AgentId,
            title: Annotated[
                Title, Field(description="Short name of the source, e.g. 'Acme API design doc'.")
            ],
            ctx: Context,
            uri: Annotated[
                Short | None,
                Field(
                    description="Where it lives (URL or path). The same uri always gives the same source id. "
                    "Omit for a pasted note: an id is derived from the title and text."
                ),
            ] = None,
            text: Annotated[Text | None, Field(description="Optional excerpt or the pasted content.")] = None,
            kind: Annotated[
                Name, Field(description="'doc', 'web', 'chat', 'note', 'tool'... (free text).")
            ] = "doc",
            trust: Annotated[
                float, Field(ge=0.0, le=1.0, description="How far this source is trusted, 0..1.")
            ] = 1.0,
            step: Step = None,
        ) -> dict[str, Any]:
            """Register WHERE knowledge comes from (a document, web page, chat or note) and get a source_id.
            Pass that source_id to assert_fact for every fact you take from it: the fact then points back at the
            source, why() can show it, and forget_source / quarantine_source can remove or isolate everything
            that came from it. Safe to repeat: the same uri returns the same source_id."""

            def work(ts: TenantState, m: MeteredClient) -> Outcome:
                where = uri.strip() if uri and uri.strip() else _note_uri(title, text or "")
                sid = _lineage(ts, m).create_source(where, kind, trust, title=title, text=text or "")
                return Outcome({"source_id": sid, "uri": where, "title": title}, created=[("Source", sid)])

            return await rt.call(ctx.headers, "add_source", agent_id, step, work)

    if "forget_source" in has:

        @tool
        async def forget_source(
            agent_id: AgentId,
            source_id: Annotated[IdStr, Field(description="Source whose derived facts should be forgotten.")],
            ctx: Context,
            step: Step = None,
        ) -> dict[str, Any]:
            """Permanently forget a source and every fact derived from it (cascade): they stop appearing in
            recall and as_of. Decisions that rested on them are flagged, not deleted. Returns the affected
            fact_ids, decision_ids and handoff_ids. Use quarantine_source instead if you are unsure (it can be
            undone)."""

            def work(ts: TenantState, m: MeteredClient) -> Outcome:
                r = _jsonable(_lineage(ts, m).forget_source(source_id))
                return Outcome({"forgotten": r}, updated=[("Fact", f) for f in r["fact_ids"]])

            return await rt.call(ctx.headers, "forget_source", agent_id, step, work)

    if "quarantine" in has:

        @tool
        async def quarantine_source(
            agent_id: AgentId,
            source_id: Annotated[IdStr, Field(description="The suspected (poisoned or wrong) source.")],
            ctx: Context,
            step: Step = None,
        ) -> dict[str, Any]:
            """Isolate a suspect source: every fact derived from it is hidden from recall and as_of right away,
            but nothing is deleted (undo with release_quarantine). Returns the blast radius: fact_ids, which
            agents/steps had READ those facts (readers, agents), and the decision_ids and handoff_ids built on
            them, so you know what to re-check."""

            def work(ts: TenantState, m: MeteredClient) -> Outcome:
                r = _jsonable(_lineage(ts, m).quarantine(source_id))
                return Outcome({"quarantined": r}, updated=[("Fact", f) for f in r["fact_ids"]])

            return await rt.call(ctx.headers, "quarantine_source", agent_id, step, work)

    if "release_quarantine" in has:

        @tool
        async def release_quarantine(
            agent_id: AgentId,
            source_id: Annotated[
                IdStr, Field(description="A source previously passed to quarantine_source.")
            ],
            ctx: Context,
            step: Step = None,
        ) -> dict[str, Any]:
            """Undo quarantine_source: the source's facts get their previous status back and show up in recall
            again. Use it when the source turned out to be fine. Returns the restored fact_ids."""

            def work(ts: TenantState, m: MeteredClient) -> Outcome:
                r = _jsonable(_lineage(ts, m).release_quarantine(source_id))
                return Outcome({"released": r}, updated=[("Fact", f) for f in r["fact_ids"]])

            return await rt.call(ctx.headers, "release_quarantine", agent_id, step, work)

    return names


def _note_uri(title: str, text: str) -> str:
    """A stable uri for a source given without one (so repeating add_source returns the same id)."""
    digest = hashlib.sha1(f"{title.strip()}\n{text.strip()}".encode()).hexdigest()[:16]  # noqa: S324
    return f"note:{digest}"
