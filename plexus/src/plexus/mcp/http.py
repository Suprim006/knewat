"""Streamable-HTTP tenant binding (ASGI middleware around the MCP SDK's Starlette app).

``/mcp/t/<tenant>`` (or ``/mcp`` + ``X-Plexus-Tenant``) is rewritten to ``/mcp`` with a trusted ``x-plexus-tenant``
header that the tools read through ``ctx.headers``. The tenant is PINNED to the MCP session when it is created;
replaying that ``mcp-session-id`` under another tenant gets a 403. Pinning fails CLOSED: a session id this
middleware holds no pin for (never issued, evicted, expired) is refused with a 404, which tells an MCP client to
initialize a new session. Pins are evicted least-recently-used. The tenant is a routing identity, not an
authenticated one (bind to loopback / put a token in front if the port leaves the machine).

``GET /healthz`` is a static liveness answer; ``GET /healthz?deep=1`` also pings the database (503 when it is down).
"""

from __future__ import annotations

import json
from collections import OrderedDict
from collections.abc import Callable
from urllib.parse import parse_qs

import anyio

from plexus.graph.tenancy import graph_name
from plexus.mcp.runtime import TENANT_HEADER

PATH_PREFIX = "/mcp/t/"
MAX_PINS = 10_000


class TenantPathMiddleware:
    def __init__(self, app, max_pins: int = MAX_PINS, health: Callable[[], object] | None = None):
        self.app = app
        self.health = health  # called by /healthz?deep=1; raises when the database is unreachable
        self.pins: OrderedDict[str, str] = OrderedDict()  # mcp-session-id -> tenant
        self.max_pins = max_pins

    @staticmethod
    async def _reply(send, status: int, message: str, key: str = "error") -> None:
        body = json.dumps({key: message}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    def _pin(self, sid: str, tenant: str) -> None:
        self.pins[sid] = tenant
        while len(self.pins) > self.max_pins:
            self.pins.popitem(last=False)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        if path == "/healthz":
            deep = "1" in parse_qs(scope.get("query_string", b"").decode("latin-1")).get("deep", [])
            if deep and self.health is not None:
                try:
                    await anyio.to_thread.run_sync(self.health)
                except Exception:
                    return await self._reply(send, 503, "unavailable", key="status")
            return await self._reply(send, 200, "ok", key="status")
        if path not in ("/mcp", "/mcp/") and not path.startswith(PATH_PREFIX):
            return await self.app(scope, receive, send)

        hdrs = list(scope["headers"])
        raw_tenant = next((v for k, v in hdrs if k.lower() == TENANT_HEADER.encode()), None)
        from_header = _text(raw_tenant)
        if raw_tenant is not None and from_header is None:
            return await self._reply(send, 400, "invalid tenant: must match ^[a-z0-9_]{1,48}$")
        from_path = path[len(PATH_PREFIX) :].split("/", 1)[0] if path.startswith(PATH_PREFIX) else None
        if from_path is not None and from_header is not None and from_path != from_header:
            return await self._reply(send, 400, "tenant in the URL and in X-Plexus-Tenant differ")
        tenant = from_path if from_path is not None else from_header
        if not tenant:
            return await self._reply(
                send, 400, "no tenant: connect to /mcp/t/<tenant> (or send X-Plexus-Tenant)"
            )
        try:
            graph_name(tenant)
        except ValueError:
            return await self._reply(send, 400, "invalid tenant: must match ^[a-z0-9_]{1,48}$")

        hdrs = [(k, v) for k, v in hdrs if k.lower() != TENANT_HEADER.encode()]
        raw_sid = next((v for k, v in hdrs if k.lower() == b"mcp-session-id"), None)
        sid = _text(raw_sid)
        if raw_sid is not None and sid is None:
            return await self._reply(send, 400, "invalid session id")
        if sid:
            pinned = self.pins.get(sid)
            if pinned is None:  # fail closed: we cannot tell which tenant this session belongs to
                return await self._reply(
                    send, 404, "unknown or expired MCP session: initialize a new session", key="error"
                )
            if pinned != tenant:
                return await self._reply(send, 403, "this MCP session is bound to a different tenant")
            self.pins.move_to_end(sid)  # least-recently-used eviction: active sessions keep their pin
        hdrs.append((TENANT_HEADER.encode(), tenant.encode()))
        scope = {**scope, "path": "/mcp", "raw_path": b"/mcp", "headers": hdrs}
        is_delete = scope["method"] == "DELETE"

        async def send_wrap(msg):
            if msg["type"] == "http.response.start":
                if not sid:
                    for k, v in msg.get("headers", []):
                        if k.lower() == b"mcp-session-id" and (new_sid := _text(v)):
                            self._pin(new_sid, tenant)
                elif is_delete and 200 <= msg["status"] < 300:
                    self.pins.pop(sid, None)
            await send(msg)

        await self.app(scope, receive, send_wrap)


def _text(raw: bytes | None) -> str | None:
    """A header value as text, or ``None`` when it is absent or not valid UTF-8."""
    if raw is None:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
