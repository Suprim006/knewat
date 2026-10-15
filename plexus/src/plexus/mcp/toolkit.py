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
from typing import Any

from mcp.server.mcpserver import Context, MCPServer

from plexus.mcp.runtime import Outcome, Runtime

WorkFn = Callable[..., Outcome]
_INJECTED = 2  # leading work-function parameters supplied by Runtime.call: (ts, m)
_CTX = "ctx"
_RESULT = dict[str, Any]


@dataclass(frozen=True)
class ToolDef:
    """One tool: its work function, and the ``Lineage`` method it needs (``None`` = always available)."""

    work: WorkFn
    requires: str | None = None

    @property
    def name(self) -> str:
        return self.work.__name__


class ToolTable:
    """The tools of one module, in definition order; :meth:`register` publishes them on an ``MCPServer``.

    ``doc_indent`` is the number of spaces the published description keeps in front of every docstring line after
    the first. The tool snapshot (``tests/mcp/snapshots/tools.json``) was recorded with the descriptions of the
    original nested definitions, whose continuation lines were indented that deep, and the snapshot is part of the
    contract; flat functions therefore re-indent their docstrings to reproduce it exactly.
    """

    def __init__(self, doc_indent: int = 8):
        self.doc_indent = doc_indent
        self._defs: list[ToolDef] = []

    def __call__(self, work: WorkFn) -> WorkFn:
        """``@tool``: add ``work`` to the table (it stays a plain function, directly callable in tests)."""
        return self.when(None)(work)

    def when(self, requires: str | None) -> Callable[[WorkFn], WorkFn]:
        """``@tool.when("create_source")``: publish the tool only if the installed ``Lineage`` has that method."""

        def add(work: WorkFn) -> WorkFn:
            _check_signature(work)
            self._defs.append(ToolDef(work, requires))
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
            mcp.tool()(_handler(rt, d.work, self.doc_indent))
            names.append(d.name)
        return names


def _check_signature(work: WorkFn) -> None:
    params = list(inspect.signature(work).parameters)
    if params[:_INJECTED] != ["ts", "m"]:
        raise TypeError(f"{work.__name__}: a tool's first two parameters must be (ts, m)")
    if "agent_id" not in params or "step" not in params or _CTX in params:
        raise TypeError(f"{work.__name__}: a tool takes agent_id and step, and never declares '{_CTX}'")


def _handler(rt: Runtime, work: WorkFn, doc_indent: int):
    """The async function FastMCP registers for ``work``.

    FastMCP derives the input schema from the handler's signature and finds the ``Context`` parameter from its
    annotations, so both are rebuilt from the work function: ``(ts, m)`` dropped, ``ctx`` inserted before the first
    parameter with a default (as in a hand-written ``def f(required, ctx, optional=...)``), result ``dict``.
    """
    name = work.__name__
    sig = inspect.signature(work, eval_str=True)
    params = list(sig.parameters.values())[_INJECTED:]
    ctx = inspect.Parameter(_CTX, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Context)
    at = next((i for i, p in enumerate(params) if p.default is not p.empty), len(params))
    params.insert(at, ctx)

    async def handler(**kwargs: Any) -> _RESULT:
        context = kwargs.pop(_CTX)
        return await rt.call(
            context.headers, name, kwargs["agent_id"], kwargs["step"], lambda ts, m: work(ts, m, **kwargs)
        )

    handler.__name__ = handler.__qualname__ = name
    handler.__module__ = work.__module__
    handler.__doc__ = _describe(work.__doc__, doc_indent)
    handler.__signature__ = sig.replace(parameters=params, return_annotation=_RESULT)  # type: ignore[attr-defined]
    handler.__annotations__ = {p.name: p.annotation for p in params} | {"return": _RESULT}
    return handler


def _describe(doc: str | None, indent: int) -> str:
    """The published description: the docstring with continuation lines indented ``indent`` spaces."""
    lines = inspect.cleandoc(doc or "").split("\n")
    return "\n".join(lines[:1] + [" " * indent + ln if ln else ln for ln in lines[1:]])
