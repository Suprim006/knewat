"""Streamable-HTTP tenant binding (ASGI middleware around the MCP SDK's Starlette app).

``/mcp/t/<tenant>`` (or ``/mcp`` + ``X-Plexus-Tenant``) is rewritten to ``/mcp`` with a trusted ``x-plexus-tenant``
header that the tools read through ``ctx.headers``. The tenant is PINNED to the MCP session when it is created;
replaying that ``mcp-session-id`` under another tenant gets a 403. The tenant is a routing identity, not an
authenticated one (bind to loopback / put a token in front if the port leaves the machine).
"""

from __future__ import annotations

import json
from collections import OrderedDict

from plexus.graph.tenancy import graph_name
from plexus.mcp.runtime import TENANT_HEADER

PATH_PREFIX = "/mcp/t/"
MAX_PINS = 10_000


class TenantPathMiddleware:
    def __init__(self, app, max_pins: int = MAX_PINS):
        self.app = app
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
            return await self._reply(send, 200, "ok", key="status")
        if path not in ("/mcp", "/mcp/") and not path.startswith(PATH_PREFIX):
            return await self.app(scope, receive, send)

        hdrs = list(scope["headers"])
        from_header = next((v.decode() for k, v in hdrs if k.lower() == TENANT_HEADER.encode()), None)
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
        sid = next((v.decode() for k, v in hdrs if k.lower() == b"mcp-session-id"), None)
        if sid and self.pins.get(sid, tenant) != tenant:
            return await self._reply(send, 403, "this MCP session is bound to a different tenant")
        hdrs.append((TENANT_HEADER.encode(), tenant.encode()))
        scope = {**scope, "path": "/mcp", "raw_path": b"/mcp", "headers": hdrs}
        is_delete = scope["method"] == "DELETE"

        async def send_wrap(msg):
            if msg["type"] == "http.response.start":
                if not sid:
                    for k, v in msg.get("headers", []):
                        if k.lower() == b"mcp-session-id":
                            self._pin(v.decode(), tenant)
                elif is_delete and 200 <= msg["status"] < 300:
                    self.pins.pop(sid, None)
            await send(msg)

        await self.app(scope, receive, send_wrap)
