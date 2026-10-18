"""One tenant's services: the Engram / Relay / Lineage / Staleness factories and scope-spec resolution."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field

from mcp.server.mcpserver.exceptions import ToolError

from knewat.embed import Embedder
from knewat.engram import Engram
from knewat.graph.client import GraphClient
from knewat.lineage import Lineage
from knewat.mcp.limits import MAX_NAME
from knewat.mcp.metering import MeteredClient
from knewat.relay import Relay
from knewat.staleness import Staleness  # P7-J

_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


@dataclass
class TenantState:
    """Services for one tenant graph (schema applied once)."""

    tenant: str
    graph: str
    client: GraphClient
    embedder: Embedder
    _scopes: dict[str, str] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    verified_at: float = field(default_factory=time.monotonic)  # last time the graph's schema was seen intact

    # -- service factories ---------------------------------------------------------------------------------
    def engram(self, m: MeteredClient) -> Engram:
        return Engram(m, self.graph, self.embedder)  # type: ignore[arg-type]

    def relay(self, m: MeteredClient) -> Relay:
        return Relay(m, self.graph)  # type: ignore[arg-type]

    def lineage(self, m: MeteredClient) -> Lineage:
        return Lineage(m, self.graph)  # type: ignore[arg-type]

    # -- P7-J staleness wiring (kept apart from the services above) --------------------------------------
    def staleness(self, m: MeteredClient) -> Staleness:
        """The staleness service for this tenant (uses the tenant's embedder for ``verify_fact``)."""
        return Staleness(m, self.graph, engram=self.engram(m))  # type: ignore[arg-type]

    # -- scope specs ---------------------------------------------------------------------------------------
    def scope_id(self, spec: str, m: MeteredClient, *, create: bool = True) -> str | None:
        """Resolve a scope spec to a Scope id: ``global`` | ``project:<name>`` | ``user:<name>`` | a scope id.

        With ``create=True`` (writes) named scopes are created on first use (idempotent MERGE); ``project:`` and
        ``user:`` scopes inherit ``global``, and a raw id is passed through (the service layer rejects an unknown
        one). With ``create=False`` (reads) nothing is ever written: the scope is looked up, and ``None`` is
        returned when it does not exist, so a typo or a probe cannot grow the graph.
        """
        spec = (spec or "global").strip()
        if len(spec) > MAX_NAME:
            raise ToolError(f"invalid scope: too long (max {MAX_NAME} characters)")
        raw = _UUID.fullmatch(spec) is not None
        if raw and create:
            return spec
        with self._lock:
            hit = self._scopes.get(spec)
        if hit:
            return hit
        kind, _, name = spec.partition(":")
        name = name.strip()
        if not raw and spec != "global" and not (kind in ("project", "user") and name):
            raise ToolError(
                f"invalid scope '{spec[:80]}': use 'global', 'project:<name>', 'user:<name>' or a scope id"
            )
        if not create:
            if raw:
                rows = m.ro(self.graph, "view/scope_lookup", {"id": spec, "kind": "", "name": ""})
            else:
                k, n = ("global", "global") if spec == "global" else (kind, name)
                rows = m.ro(self.graph, "view/scope_lookup", {"id": "", "kind": k, "name": n})
            if not rows:
                return None
            sid = rows[0]["id"]
        else:
            eng = self.engram(m)
            if spec == "global":
                sid = eng.create_scope("global", "global")
            else:
                parent = self.scope_id("global", m)
                sid = eng.create_scope(kind, name, inherits=[parent])
        with self._lock:
            self._scopes[spec] = sid
        return sid
