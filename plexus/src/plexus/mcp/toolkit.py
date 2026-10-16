"""The one tool-definition pattern shared by every MCP tool module.

A tool is a plain, flat *work function*::

    @tool
    def pin_fact(ts: TenantState, m: MeteredClient, agent_id: AgentId, fact_id: IdStr, step: Step = None) -> Outcome:
        '''What the tool does, for the model that reads the tool list.'''
        ...
        return Outcome({...}, updated=[("Fact", fact_id)])

The first two parameters (``ts``, ``m``) are supplied by :meth:`Runtime.call`; every other parameter is an argument
of the published tool, so the signature *is* the argument schema (``Annotated`` types and their ``Field``
descriptions sit right next to the body). ``agent_id`` and ``step`` are mandatory on every tool.
:meth:`ToolTable.register` wraps each work function in the handler FastMCP needs: it injects the request
``Context`` and runs the function through ``rt.call`` (tenant binding, timing, ``ToolCall`` + ``Step`` audit,
error mapping), so no tool repeats that plumbing.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass
from typing import Annotated, Any, ClassVar, Literal

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from plexus.mcp.audit_policy import ToolKind
from plexus.mcp.runtime import Outcome, Runtime

WorkFn = Callable[..., Outcome]
_INJECTED = 2  # leading work-function parameters supplied by Runtime.call: (ts, m)
_CTX = "ctx"
_RESULT = dict[str, Any]
_AUDIT = "audit"  # the optional per-call argument every read tool gets (see plexus.mcp.audit_policy)
AuditArg = Annotated[
    Literal["light", "full"] | None,
    Field(
        description="Optional. 'light' = record only a ToolCall for this read (no Step, no Recall/READ edges): "
        "cheaper under load. It can only lower the audit level the server applies to this tenant, never raise it."
    ),
]


@dataclass(frozen=True)
class ToolDef:
    """One tool: its work function, the ``Lineage`` method it needs (``None`` = always available) and its class.

    ``kind`` is ``'write'`` unless the tool declares ``'read'`` (a forgotten annotation is the safe one: audited in
    full and refused on a read-only tenant). A ``'read'`` tool never writes domain data: the runtime enforces that on
    read-only tenants and demotes the call to full audit if it ever does. ``exposure`` marks a read whose ``READ``
    edges are provenance (``recall``): its audit is not lowered by the tenant mode, only by an explicit ``audit``.
    """

    work: WorkFn
    requires: str | None = None
    kind: ToolKind = "write"
    exposure: bool = False

    @property
    def name(self) -> str:
        return self.work.__name__


class ToolTable:
    """The tools of one module, in definition order; :meth:`register` publishes them on an ``MCPServer``.

    A tool's published description is its (cleaned) docstring.
    """

    _tables: ClassVar[list[ToolTable]] = []  # every table ever made: all_tool_defs() reads them

    def __init__(self, *, listed: bool = True):
        self._defs: list[ToolDef] = []
        if listed:  # False for throwaway tables (tests): they must not show up in all_tool_defs()
            ToolTable._tables.append(self)

    def __call__(
        self, work: WorkFn | None = None, *, kind: ToolKind = "write", exposure: bool = False
    ) -> Any:
        """``@tool`` or ``@tool(kind="read")``: add ``work`` to the table (it stays a plain function)."""
        add = self.when(None, kind=kind, exposure=exposure)
        return add if work is None else add(work)

    def when(
        self, requires: str | None, *, kind: ToolKind = "write", exposure: bool = False
    ) -> Callable[[WorkFn], WorkFn]:
        """``@tool.when("create_source")``: publish the tool only if the installed ``Lineage`` has that method."""
        if exposure and kind != "read":
            raise TypeError("exposure=True only makes sense for a read tool")

        def add(work: WorkFn) -> WorkFn:
            _check_signature(work)
            self._defs.append(ToolDef(work, requires, kind, exposure))
            return work

        return add

    def __iter__(self) -> Iterator[ToolDef]:
        return iter(self._defs)

    def register(self, mcp: MCPServer, rt: Runtime, available: Collection[str] | None = None) -> list[str]:
        """Register the tools on ``mcp`` and return their names. ``available`` filters ``requires``-gated tools
        (``None`` means every gated tool is available)."""
        names: list[str] = []
        for d in self._defs:
            if d.requires is not None and available is not None and d.requires not in available:
                continue
            mcp.tool()(_handler(rt, d))
            names.append(d.name)
        return names


def all_tool_defs() -> list[ToolDef]:
    """Every tool declared on any :class:`ToolTable` (import the tool modules first, e.g. ``plexus.mcp.server``)."""
    return [d for table in ToolTable._tables for d in table]


def _check_signature(work: WorkFn) -> None:
    params = list(inspect.signature(work).parameters)
    if params[:_INJECTED] != ["ts", "m"]:
        raise TypeError(f"{work.__name__}: a tool's first two parameters must be (ts, m)")
    if "agent_id" not in params or "step" not in params or _CTX in params:
        raise TypeError(f"{work.__name__}: a tool takes agent_id and step, and never declares '{_CTX}'")
    if _AUDIT in params:
        raise TypeError(
            f"{work.__name__}: '{_AUDIT}' is added by the toolkit to read tools; do not declare it"
        )


def _handler(rt: Runtime, d: ToolDef):
    """The async function FastMCP registers for ``work``.

    FastMCP derives the input schema from the handler's signature and finds the ``Context`` parameter from its
    annotations, so both are rebuilt from the work function: ``(ts, m)`` dropped, ``ctx`` inserted before the first
    parameter with a default (as in a hand-written ``def f(required, ctx, optional=...)``), result ``dict``.
    """
    work, name = d.work, d.name
    sig = inspect.signature(work, eval_str=True)
    params = list(sig.parameters.values())[_INJECTED:]
    ctx = inspect.Parameter(_CTX, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Context)
    at = next((i for i, p in enumerate(params) if p.default is not p.empty), len(params))
    params.insert(at, ctx)
    if (
        d.kind == "read"
    ):  # the per-call audit level: offered on read tools only, never upgrades the tenant mode
        params.append(
            inspect.Parameter(_AUDIT, inspect.Parameter.KEYWORD_ONLY, default=None, annotation=AuditArg)
        )

    async def handler(**kwargs: Any) -> _RESULT:
        context = kwargs.pop(_CTX)
        audit = kwargs.pop(_AUDIT, None)
        return await rt.call(
            context.headers,
            name,
            kwargs["agent_id"],
            kwargs["step"],
            lambda ts, m: work(ts, m, **kwargs),
            kind=d.kind,
            exposure=d.exposure,
            audit=audit,
        )

    handler.__name__ = handler.__qualname__ = name
    handler.__module__ = work.__module__
    handler.__doc__ = inspect.cleandoc(work.__doc__ or "")
    handler.__signature__ = sig.replace(parameters=params, return_annotation=_RESULT)  # type: ignore[attr-defined]
    handler.__annotations__ = {p.name: p.annotation for p in params} | {"return": _RESULT}
    return handler
