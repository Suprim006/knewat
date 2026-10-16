"""Toolsets: which of the Plexus tools one MCP session publishes (P12, scoped tool exposure).

Every tool is re-read by the model on every API call (the tool list is part of the prompt), so a session that
only coordinates should not pay for the staleness, forgetting or dedup tools in its prompt. A *toolset* is a
comma-separated list of names, each either a **module** (the module boundaries of ``docs/PLEXUS_REPORT.md``
§2.2, one :class:`~plexus.mcp.toolkit.ToolTable` each) or a **profile** (a documented union of modules):

=============  ==========================================================================================
``engram``      memory: sessions, episodes, facts, recall, fact history, procedures (7)
``relay``       coordination: agents, task DAG, claims, leases, handoffs, decisions, artifacts (13)
``lineage``     provenance and time: sources, why, who knew, knew at, as of, forgetting, quarantine (9)
``staleness``   facts anchored to code, change reports, re-verification, review dates (7)
``forgetting``  pin / unpin, memory strength, sweep, restore (5)
``relations``   typed entity relations and the read-only ``impact`` blast radius (2)
``dedup``       confirm / reject a possible duplicate (2)
``core``        profile: ``engram,relay,lineage`` (the P0-P6 product)
``full``        profile: every module (the default; unchanged behaviour)
=============  ==========================================================================================

Selection: ``plexus-mcp --toolset core`` (or env ``PLEXUS_TOOLSET``) sets a process default; over HTTP a client
picks per session with ``/mcp/t/<tenant>?toolset=core`` or the ``X-Plexus-Toolset`` header, pinned to the MCP
session like the tenant. An unknown name is an error, never a silent ``full`` or an empty list. A tool outside the
session's toolset is neither listed nor callable. A toolset is a prompt-size choice, **not access control**: any
client can open another session with ``toolset=full`` (read-only tenants and audit modes are the safety controls).
"""

from __future__ import annotations

import os

from plexus.mcp.lineage_tools import LINEAGE_TOOLS
from plexus.mcp.memory_tools import MEMORY_TOOLS
from plexus.mcp.staleness_tools import STALENESS_TOOLS
from plexus.mcp.toolkit import ToolTable
from plexus.mcp.tools_dedup import DEDUP_TOOLS
from plexus.mcp.tools_engram import ENGRAM_TOOLS
from plexus.mcp.tools_impact import IMPACT_TOOLS
from plexus.mcp.tools_relations import RELATION_TOOLS
from plexus.mcp.tools_relay import RELAY_TOOLS

TOOLSET_HEADER = "x-plexus-toolset"
TOOLSET_ENV = "PLEXUS_TOOLSET"
FULL = "full"

_MODULE_TABLES: dict[str, tuple[ToolTable, ...]] = {
    "engram": (ENGRAM_TOOLS,),
    "relay": (RELAY_TOOLS,),
    "lineage": (LINEAGE_TOOLS,),
    "staleness": (STALENESS_TOOLS,),
    "forgetting": (MEMORY_TOOLS,),
    "relations": (RELATION_TOOLS, IMPACT_TOOLS),
    "dedup": (DEDUP_TOOLS,),
}
MODULES: dict[str, frozenset[str]] = {
    name: frozenset(d.name for t in tables for d in t) for name, tables in _MODULE_TABLES.items()
}
PROFILES: dict[str, tuple[str, ...]] = {
    "core": ("engram", "relay", "lineage"),
    FULL: tuple(MODULES),
}
VALID_NAMES: tuple[str, ...] = (*MODULES, *PROFILES)


class ToolsetError(ValueError):
    """An unknown or empty toolset name (the message lists the valid names)."""


def modules_of(spec: str) -> tuple[str, ...]:
    """The modules a toolset spec names, in :data:`MODULES` order: ``"core,dedup"`` ->
    ``("engram", "relay", "lineage", "dedup")``. Raises :class:`ToolsetError` for an unknown or empty name."""
    parts = [p.strip().lower() for p in spec.split(",")]
    if not spec.strip() or any(not p for p in parts):
        raise ToolsetError(f"empty toolset name in {spec!r}; valid: {', '.join(VALID_NAMES)}")
    picked: set[str] = set()
    for p in parts:
        if p in MODULES:
            picked.add(p)
        elif p in PROFILES:
            picked.update(PROFILES[p])
        else:
            raise ToolsetError(f"unknown toolset {p!r}; valid: {', '.join(VALID_NAMES)}")
    return tuple(m for m in MODULES if m in picked)


def canonical(spec: str) -> str:
    """One spelling per toolset (``"Relay, engram"`` and ``"engram,relay"`` -> ``"engram,relay"``; a module set
    that is a profile -> the profile's name, e.g. ``"core"``), so a session pin compares toolsets, not strings."""
    mods = modules_of(spec)
    named = next((p for p, pm in PROFILES.items() if set(pm) == set(mods)), None)
    return named or ",".join(mods)


def tool_names(spec: str) -> frozenset[str]:
    """Every tool name in the toolset (a gated tool may still be absent from a server that lacks its backend)."""
    return frozenset().union(*(MODULES[m] for m in modules_of(spec)))


def default_toolset(value: str | None = None) -> str:
    """The process default: ``value`` (the ``--toolset`` flag), else env ``PLEXUS_TOOLSET``, else ``full``;
    canonical, and raising :class:`ToolsetError` on a bad value so a misconfigured server fails at start."""
    if value is not None:
        return canonical(value)
    env = os.environ.get(TOOLSET_ENV, "").strip()  # unset or empty env = the default
    return canonical(env) if env else FULL


def module_of(tool: str) -> str | None:
    """The module a tool belongs to (``None`` for a name that is no Plexus tool)."""
    return next((m for m, names in MODULES.items() if tool in names), None)
