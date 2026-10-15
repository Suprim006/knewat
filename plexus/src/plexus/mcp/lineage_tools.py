"""Lineage MCP tools, registered only when ``plexus.lineage`` exists (P2-D merges separately).

``plexus.lineage.Lineage(client, graph)`` provides ``why``, ``why_recalled``, ``who_knew``, ``knew_at``, ``as_of``,
``create_source``, ``forget_source``, ``quarantine`` and ``release_quarantine``; a method that is missing is simply
not exposed as a tool (each tool below names the method it needs with ``@tool.when(...)``). Step recording and
READ/WROTE/Recall attachment for every call live in ``plexus.mcp.runtime``.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import logging
import sys
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
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
from plexus.mcp.toolkit import ToolTable

log = logging.getLogger("plexus.mcp")

LINEAGE_TOOLS = ToolTable()
tool = LINEAGE_TOOLS


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


def _note_uri(title: str, text: str) -> str:
    """A stable uri for a source given without one (so repeating add_source returns the same id)."""
    digest = hashlib.sha1(f"{title.strip()}\n{text.strip()}".encode()).hexdigest()[:16]  # noqa: S324
    return f"note:{digest}"


def register_lineage(mcp: MCPServer, rt: Runtime) -> list[str]:
    """Register whichever Lineage tools the installed ``plexus.lineage`` provides. Returns their names."""
    if not lineage_available():
        return []
    mod = importlib.import_module("plexus.lineage")
    cls = getattr(mod, "Lineage", None)
    if cls is None:
        log.warning("plexus.lineage has no Lineage class; Lineage tools not registered")
        return []
    has = {d.requires for d in LINEAGE_TOOLS if d.requires and hasattr(cls, d.requires)}
    return LINEAGE_TOOLS.register(mcp, rt, has)


# ---------------------------------------------------------------- explain and time machine
@tool.when("why")
def why(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    node_id: Annotated[IdStr, Field(description="A decision id or a fact id.")],
    step: Step = None,
) -> Outcome:
    """Explain WHY a decision was made (or where a fact comes from): the graph paths from a decision_id
    or fact_id to the facts it rests on, who asserted them, their sources, and the steps that wrote them."""
    return Outcome({"why": _jsonable(_lineage(ts, m).why(node_id))})


@tool.when("why_recalled")
def why_recalled(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    recall_id: Annotated[IdStr, Field(description="A recall id.")],
    step: Step = None,
) -> Outcome:
    """Explain why a past recall returned the facts it did. The recall_id comes from the recall tool's
    result. Gives the query, each returned fact in rank order with its score, and where it came from."""
    return Outcome({"why_recalled": _jsonable(_lineage(ts, m).why_recalled(recall_id))})


@tool.when("who_knew")
def who_knew(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    fact_id: Annotated[IdStr, Field(description="A fact id.")],
    step: Step = None,
) -> Outcome:
    """Which agents asserted, wrote or READ a fact, and at which step: who knew this, and since when."""
    return Outcome({"who_knew": _jsonable(_lineage(ts, m).who_knew(fact_id))})


@tool.when("knew_at")
def knew_at(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    subject_agent: Annotated[IdStr, Field(description="The agent whose knowledge to reconstruct.")],
    step_n: Annotated[int, Field(description="The step number.", ge=0, le=MAX_INT)],
    step: Step = None,
) -> Outcome:
    """Time machine: what a given agent knew at its step N (the facts it had read that were still valid
    then) and everything it had written by then."""
    return Outcome({"knew_at": _jsonable(_lineage(ts, m).knew_at(subject_agent, step_n))})


@tool.when("as_of")
def as_of(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    subject: Annotated[NameReq, Field(description="Fact subject.")],
    predicate: Annotated[NameReq, Field(description="Fact attribute.")],
    t: Annotated[EpochMs, Field(description="Epoch milliseconds.")],
    scope: ScopeArg = "global",
    step: Step = None,
) -> Outcome:
    """The value a (subject, predicate) had at time t (epoch ms), or null if it had none yet. Forgotten
    and quarantined facts never answer."""
    sid = ts.scope_id(scope, m, create=False)  # a read never creates a Scope
    if sid is None:
        return Outcome({"as_of": None})
    return Outcome({"as_of": _jsonable(_lineage(ts, m).as_of(subject, predicate, t, sid))})


# ---------------------------------------------------------------- sources
@tool.when("create_source")
def add_source(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    title: Annotated[Title, Field(description="Short name of the source, e.g. 'Acme API design doc'.")],
    uri: Annotated[
        Short | None,
        Field(
            description="Where it lives (URL or path). The same uri always gives the same source id. "
            "Omit for a pasted note: an id is derived from the title and text."
        ),
    ] = None,
    text: Annotated[Text | None, Field(description="Optional excerpt or the pasted content.")] = None,
    kind: Annotated[Name, Field(description="'doc', 'web', 'chat', 'note', 'tool'... (free text).")] = "doc",
    trust: Annotated[
        Literal["normal", "high"] | Annotated[float, Field(ge=0.0, le=1.0)] | None,
        Field(
            description="'high' for a source you fully trust: facts derived from it are protected from "
            "fading in recall. 'normal' (default). A number 0..1 is accepted for older clients and means "
            "'normal'; leaving it out keeps the trust an existing source already has."
        ),
    ] = None,
    step: Step = None,
) -> Outcome:
    """Register WHERE knowledge comes from (a document, web page, chat or note) and get a source_id.
    Pass that source_id to assert_fact for every fact you take from it: the fact then points back at the
    source, why() can show it, and forget_source / quarantine_source can remove or isolate everything
    that came from it. Safe to repeat: the same uri returns the same source_id."""
    where = uri.strip() if uri and uri.strip() else _note_uri(title, text or "")
    sid = _lineage(ts, m).create_source(where, kind, trust, title=title, text=text or "")
    return Outcome({"source_id": sid, "uri": where, "title": title}, created=[("Source", sid)])


@tool.when("forget_source")
def forget_source(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    source_id: Annotated[IdStr, Field(description="Source whose derived facts should be forgotten.")],
    step: Step = None,
) -> Outcome:
    """Permanently forget a source and every fact derived from it (cascade): they stop appearing in
    recall and as_of. Decisions that rested on them are flagged, not deleted. Returns the affected
    fact_ids, decision_ids and handoff_ids. Use quarantine_source instead if you are unsure (it can be
    undone)."""
    r = _jsonable(_lineage(ts, m).forget_source(source_id))
    return Outcome({"forgotten": r}, updated=[("Fact", f) for f in r["fact_ids"]])


@tool.when("quarantine")
def quarantine_source(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    source_id: Annotated[IdStr, Field(description="The suspected (poisoned or wrong) source.")],
    step: Step = None,
) -> Outcome:
    """Isolate a suspect source: every fact derived from it is hidden from recall and as_of right away,
    but nothing is deleted (undo with release_quarantine). Returns the blast radius: fact_ids, which
    agents/steps had READ those facts (readers, agents), and the decision_ids and handoff_ids built on
    them, so you know what to re-check."""
    r = _jsonable(_lineage(ts, m).quarantine(source_id))
    return Outcome({"quarantined": r}, updated=[("Fact", f) for f in r["fact_ids"]])


@tool.when("release_quarantine")
def release_quarantine(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    source_id: Annotated[IdStr, Field(description="A source previously passed to quarantine_source.")],
    step: Step = None,
) -> Outcome:
    """Undo quarantine_source: the source's facts get their previous status back and show up in recall
    again. Use it when the source turned out to be fine. Returns the restored fact_ids."""
    r = _jsonable(_lineage(ts, m).release_quarantine(source_id))
    return Outcome({"released": r}, updated=[("Fact", f) for f in r["fact_ids"]])
