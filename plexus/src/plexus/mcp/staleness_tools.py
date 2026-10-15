"""Staleness MCP tools (P7-J, D-011): code changes make memories suspect; agents re-verify them.

``anchor_fact`` / ``describe_code`` link memory to code, ``mark_changed`` is called by the hooks of
``plexus.codescan`` (git post-commit, Claude Code PostToolUse), ``facts_to_verify`` / ``docs_to_update`` are the work
lists and ``verify_fact`` records the outcome of a re-check. Every tool is one service call; :meth:`Runtime.call`
times it, records the ``ToolCall`` and the agent's ``Step``. Facts a call made suspect or verified are ``WROTE`` edges
of the Step (through the ``after`` hook, because ``Fact`` is not a ``WROTE_LABELS`` label); a created ``Change`` is a
``CREATED`` edge of the ToolCall. Reading ``facts_to_verify`` does NOT add ``READ`` edges: a suspect fact must not be
strengthened by being listed (D-012).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from plexus.mcp.limits import (
    MAX_LIST,
    AgentId,
    EpochMs,
    IdStr,
    Name,
    Short,
    Step,
    StrictModel,
    Value,
)
from plexus.mcp.runtime import LINK_CHUNK, MeteredClient, Outcome, Runtime, TenantState
from plexus.mcp.toolkit import ToolTable

MAX_PATH = 1024
MAX_HASH = 128
MAX_CHANGES = 200  # = plexus.staleness.service.MAX_CHANGES

PathStr = Annotated[str, Field(min_length=1, max_length=MAX_PATH)]
HashStr = Annotated[str, Field(max_length=MAX_HASH)]
Symbol = Annotated[str, Field(max_length=512)]

STALENESS_TOOLS = ToolTable()
tool = STALENESS_TOOLS


class ChangeSpec(StrictModel):
    path: PathStr = Field(
        description="Absolute path of the changed file (any slash style; it is normalised)."
    )
    symbol: Symbol = Field(
        default="", description="'' for the whole file, else a dotted name like 'PaymentService.create'."
    )
    new_hash: HashStr = Field(
        description="Hash of the file / symbol now (required). Send '' explicitly when it no longer exists."
    )
    old_hash: HashStr = Field(
        default="",
        description="Hash before the change, if you know it. Used only when Plexus has no hash stored yet.",
    )
    kind: Literal["file", "function", "class"] | None = Field(
        default=None, description="Optional: 'class' for a class symbol (default: function / file)."
    )


def _wrote_facts(fact_ids: list[str]):
    """An ``Outcome.after`` hook: the Step WROTE these facts (chunked to the link_step limit)."""
    ids = list(dict.fromkeys(fact_ids))

    def after(lin: Any, step_id: str | None) -> dict[str, Any] | None:
        for i in range(0, len(ids), LINK_CHUNK):
            lin.link_step(step_id, wrote_ids=ids[i : i + LINK_CHUNK])
        return None

    return after if ids else None


def _anchor_outcome(r: dict[str, Any], owner: tuple[str, str]) -> Outcome:
    """Audit edges of an anchor call: a new CodeAnchor is CREATED, an existing one is UPDATED with ``owner``."""
    ref = ("CodeAnchor", r["anchor_id"])
    return Outcome(
        r, created=[ref] if r["created"] else [], updated=[owner] + ([] if r["created"] else [ref])
    )


def register_staleness(mcp: MCPServer, rt: Runtime) -> list[str]:
    """Register the 7 staleness tools on ``mcp``; returns their names."""
    return STALENESS_TOOLS.register(mcp, rt)


# ---------------------------------------------------------------- linking memory to code
@tool
def anchor_fact(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    fact_id: Annotated[IdStr, Field(description="The fact that depends on this code.")],
    path: Annotated[
        PathStr,
        Field(description="Absolute path of the file the fact is about (e.g. C:/repo/app/payments.py)."),
    ],
    symbol: Annotated[
        Symbol,
        Field(
            description="Optional Python function / class, dotted: 'PaymentService.create'. '' = whole file."
        ),
    ] = "",
    hash: Annotated[
        HashStr, Field(description="Optional hash of that code now (stored only if none is stored yet).")
    ] = "",
    step: Step = None,
) -> Outcome:
    """Tie a fact to the code it is about (a file, or a Python function / class). When that code changes, the
    fact becomes SUSPECT and shows up in facts_to_verify. Facts derived from a Source whose uri is a file path
    are tied to that file automatically; use this for precision (one function) or for facts with no Source."""
    return _anchor_outcome(ts.staleness(m).anchor_fact(fact_id, path, symbol, hash), ("Fact", fact_id))


@tool
def describe_code(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    source_id: Annotated[
        IdStr, Field(description="The doc Source (from add_source) that describes the code.")
    ],
    path: Annotated[PathStr, Field(description="Absolute path of the code file it describes.")],
    symbol: Annotated[Symbol, Field(description="Optional function / class; '' = whole file.")] = "",
    hash: Annotated[HashStr, Field(description="Optional hash of that code now.")] = "",
    step: Step = None,
) -> Outcome:
    """Record that a document (a Source) describes a piece of code. When the code changes, docs_to_update lists
    the document so it can be brought up to date."""
    r = ts.staleness(m).describe_code(source_id, path, symbol, hash)
    return _anchor_outcome(r, ("Source", source_id))


# ---------------------------------------------------------------- code changes and re-verification
@tool
def mark_changed(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    changes: Annotated[
        list[ChangeSpec],
        Field(min_length=1, max_length=MAX_CHANGES, description="The files / symbols whose content changed."),
    ],
    commit: Annotated[Name, Field(description="Commit id, or '' for a working-tree edit.")] = "",
    at: Annotated[
        EpochMs | None, Field(description="When the change happened (epoch ms); default now.")
    ] = None,
    step: Step = None,
) -> Outcome:
    """Report that code changed (normally called by the git post-commit / Claude Code edit hooks, see
    `plexus code`). Memories that depend on a changed file or function become SUSPECT, not false: they stay
    recallable but are flagged. A first sighting of a file with no old_hash is just a baseline. Returns the
    suspect fact_ids, the decisions built on them, and the docs that describe the changed code. If truncated
    is true, call again with the same arguments (and the returned 'at') to continue."""
    r = ts.staleness(m).mark_changed([c.model_dump(exclude_none=True) for c in changes], commit, at, agent_id)
    return Outcome(
        r,
        created=[("Change", r["change_id"])] if r["change_id"] else [],
        updated=[("Fact", f) for f in r["suspect_fact_ids"]],
        after=_wrote_facts(r["suspect_fact_ids"]),
    )


@tool
def verify_fact(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    fact_id: Annotated[IdStr, Field(description="The suspect fact you re-checked.")],
    still_true: Annotated[bool, Field(description="True if it still holds, false if it changed.")],
    new_value: Annotated[
        Value, Field(description="Required when still_true is false: the value it has now.")
    ] = "",
    evidence: Annotated[
        Short,
        Field(
            description="Optional: where you checked (an absolute file path or URL becomes a Source) or a note."
        ),
    ] = "",
    commit: Annotated[Name, Field(description="Optional commit id you verified against.")] = "",
    step: Step = None,
) -> Outcome:
    """Record the outcome of re-checking a suspect fact (see facts_to_verify). still_true=true marks it
    verified. still_true=false needs new_value: the new value is asserted, the old one is superseded as of the
    moment the code changed (history stays correct), and decisions that rested on the old value are flagged."""
    r = ts.staleness(m).verify_fact(fact_id, still_true, new_value, evidence, agent_id, commit)
    created = [("Fact", r["new_fact_id"])] if "new_fact_id" in r else []
    updated = [("Fact", fact_id), *(("Decision", d) for d in r["flagged_decisions"])]
    wrote = [fact_id, *([r["new_fact_id"]] if "new_fact_id" in r else [])]
    return Outcome(r, created=created, updated=updated, after=_wrote_facts(wrote))


# ---------------------------------------------------------------- work lists
@tool
def facts_to_verify(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    scope: Annotated[
        str,
        Field(
            max_length=512,
            description="Optional: only this scope ('global', 'project:<name>', 'user:<name>') and what it "
            "inherits. Default: every scope.",
        ),
    ] = "",
    limit: Annotated[int, Field(ge=1, le=MAX_LIST, description="Max facts to return.")] = 50,
    step: Step = None,
) -> Outcome:
    """List the memories that may be stale: facts whose code changed since they were last verified, or whose
    review date passed, most important first (decisions that depend on them, then oldest suspicion). Re-check
    the ones you are about to rely on, then call verify_fact."""
    sid = ""
    if scope.strip():
        found = ts.scope_id(scope, m, create=False)
        if found is None:
            return Outcome({"facts": [], "count": 0})
        sid = found
    rows = ts.staleness(m).facts_to_verify(sid, limit)
    return Outcome({"facts": rows, "count": len(rows)})


@tool
def docs_to_update(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    since: Annotated[EpochMs, Field(description="Only changes after this time (epoch ms).")] = 0,
    limit: Annotated[int, Field(ge=1, le=MAX_LIST, description="Max documents to return.")] = 50,
    step: Step = None,
) -> Outcome:
    """List documents that describe code which has changed since the document was last edited (see
    describe_code), newest change first, with the commits and paths that changed."""
    rows = ts.staleness(m).docs_to_update(since, limit)
    return Outcome({"docs": rows, "count": len(rows)})


@tool
def set_review_date(
    ts: TenantState,
    m: MeteredClient,
    agent_id: AgentId,
    fact_id: Annotated[IdStr, Field(description="A fact that is not about code (a URL, account, request).")],
    verify_after: Annotated[
        EpochMs,
        Field(description="Epoch ms after which the fact must be re-checked. 9999999999999 clears it."),
    ],
    step: Step = None,
) -> Outcome:
    """Give a fact a review date. After that time it appears in facts_to_verify, so facts that no code change
    can invalidate (a deployed URL, an account, a client request) are re-checked on a schedule."""
    r = ts.staleness(m).set_review_date(fact_id, verify_after)
    return Outcome(r, updated=[("Fact", fact_id)], after=_wrote_facts([fact_id]))
