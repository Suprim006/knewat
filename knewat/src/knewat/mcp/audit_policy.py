"""Audit modes: how much a tool call writes besides its own work (PRODUCT_FIXES A, P9-e).

Three modes, decided per tenant (env) and lowered per call (``audit`` argument on read tools):

* ``full``  - today: a ``Step`` (+ WROTE/READ edges), the ``Recall`` record of ``recall``, and a ``ToolCall``.
* ``light`` - a read tool writes one ``ToolCall {wrote: false}`` and nothing else. Write tools are unchanged.
* ``off``   - a read tool writes nothing. A write tool is refused. A tenant in this mode is never created by a request.

``recall`` is the one *exposure* tool: its ``READ`` edges feed ``who_knew`` / ``knew_at`` / forgetting, so on a tenant
that is not ``off`` it stays ``full`` unless the caller asks for ``audit='light'`` for that call.

Configuration (read once, at :class:`~plexus.mcp.runtime.Runtime` start; a bad value fails loudly):

* ``PLEXUS_AUDIT_MODE``  - the default tenant mode (default ``full``).
* ``PLEXUS_AUDIT_MODES`` - ``"demo*=off,team_*=full"``: ``glob=mode`` pairs, first match wins, matched on the tenant id.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Literal

AuditMode = Literal["off", "light", "full"]
ToolKind = Literal["read", "write"]

MODES: tuple[str, ...] = ("off", "light", "full")
_RANK = {m: i for i, m in enumerate(MODES)}
ENV_DEFAULT = "PLEXUS_AUDIT_MODE"
ENV_TABLE = "PLEXUS_AUDIT_MODES"


def _mode(value: str, where: str) -> AuditMode:
    v = value.strip().lower()
    if v not in _RANK:
        raise ValueError(f"{where}: audit mode must be one of {', '.join(MODES)}, got {value!r}")
    return v  # type: ignore[return-value]


def parse_table(text: str) -> tuple[tuple[str, AuditMode], ...]:
    """``"demo*=off, team_*=full"`` -> ``(("demo*", "off"), ("team_*", "full"))``."""
    out: list[tuple[str, AuditMode]] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        pattern, sep, mode = part.partition("=")
        pattern = pattern.strip()
        if not sep or not pattern:
            raise ValueError(f"{ENV_TABLE}: expected 'glob=mode', got {part!r}")
        out.append((pattern, _mode(mode, ENV_TABLE)))
    return tuple(out)


@dataclass(frozen=True)
class AuditPolicy:
    """The tenant -> mode table and the rules that turn (tenant mode, tool class, request) into one call's mode."""

    default: AuditMode = "full"
    overrides: tuple[tuple[str, AuditMode], ...] = ()

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> AuditPolicy:
        env = os.environ if environ is None else environ
        return cls(
            default=_mode(env.get(ENV_DEFAULT) or "full", ENV_DEFAULT),
            overrides=parse_table(env.get(ENV_TABLE) or ""),
        )

    def tenant_mode(self, tenant: str) -> AuditMode:
        for pattern, mode in self.overrides:
            if fnmatchcase(tenant, pattern):
                return mode
        return self.default

    def effective(
        self, tenant: str, kind: ToolKind, exposure: bool = False, requested: str | None = None
    ) -> AuditMode:
        """The mode of one call. ``off`` for a write tool means *refused* (the caller raises).

        ``requested`` is the per-call ``audit`` argument: it can only lower a read call to ``light``.
        """
        tenant_mode = self.tenant_mode(tenant)
        if kind == "write":
            return "off" if tenant_mode == "off" else "full"
        if tenant_mode == "off":
            return "off"
        mode: AuditMode = "full" if exposure else tenant_mode
        if requested == "light" and _RANK[mode] > _RANK["light"]:
            mode = "light"
        return mode
