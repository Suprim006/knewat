# ruff: noqa: E501  (long prose lines, as in mcp/ and cli.py)
"""A dependency-light MCP streamable-HTTP client for the hooks (stdlib only).

``import mcp`` costs about two seconds on a cold Windows machine, which would blow the budget of a Claude Code
``PostToolUse`` hook (it runs after EVERY edit and must finish in under 2 s). The hook only needs three requests of
the streamable-HTTP transport (``initialize``, ``notifications/initialized``, ``tools/call``), so it speaks them
directly. ``scan`` and ``baseline`` use the ``mcp`` package client (:mod:`plexus.codescan.client`); both are tested
against the same real server. Same interface: ``await session.call(tool, **args)``.
"""

from __future__ import annotations

import asyncio
import http.client
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

from plexus.codescan.client import McpCallError, tenant_path, tool_arguments, tool_result

PROTOCOL_VERSION = "2025-06-18"


class FastSession:
    """One MCP session over a keep-alive HTTP connection; ``call`` mirrors ``client.Session.call``."""

    def __init__(self, url: str, tenant: str, agent_id: str, deadline: float):
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise McpCallError(f"bad Plexus url '{url[:80]}'")
        self.url = url
        self.path = tenant_path(parts.path, tenant)
        self.agent_id = agent_id
        self.deadline = deadline
        cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        self._conn = cls(parts.hostname, parts.port, timeout=self._left())
        self._session_id: str | None = None
        self._next_id = 0

    def _left(self) -> float:
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise McpCallError("timed out")
        return left

    def _post(self, body: dict[str, Any]) -> tuple[int, str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        self._conn.timeout = self._left()
        if self._conn.sock is not None:
            self._conn.sock.settimeout(self._conn.timeout)
        try:
            self._conn.request("POST", self.path, json.dumps(body), headers)
            resp = self._conn.getresponse()
            data = resp.read().decode("utf-8", errors="replace")
        except (OSError, http.client.HTTPException) as exc:
            raise McpCallError(
                f"cannot reach Plexus at {self.url}: {type(exc).__name__}: {exc}"[:200]
            ) from exc
        sid = resp.getheader("Mcp-Session-Id")
        if sid:
            self._session_id = sid
        return resp.status, resp.getheader("Content-Type") or "", data

    @staticmethod
    def _message(content_type: str, data: str) -> dict[str, Any]:
        """The JSON-RPC message of a response (plain JSON, or the last ``data:`` event of an SSE stream)."""
        if "text/event-stream" in content_type:
            events = [ln[5:].strip() for ln in data.splitlines() if ln.startswith("data:")]
            if not events:
                raise McpCallError("empty event stream from the Plexus server")
            return json.loads(events[-1])
        return json.loads(data)

    def open(self) -> None:
        status, ctype, data = self._post(
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "plexus-hook", "version": "0"},
                },
            }
        )
        if status != 200:
            raise McpCallError(f"Plexus answered HTTP {status} to initialize: {data[:120]}")
        self._message(ctype, data)
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    async def call(self, tool: str, /, **args: Any) -> dict[str, Any]:
        self._next_id += 1
        status, ctype, data = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id,
                "method": "tools/call",
                "params": {"name": tool, "arguments": tool_arguments(self.agent_id, args)},
            }
        )
        if status != 200:
            raise McpCallError(f"Plexus answered HTTP {status} to {tool}: {data[:120]}")
        msg = self._message(ctype, data)
        if "error" in msg:
            raise McpCallError(str(msg["error"].get("message", msg["error"]))[:300])
        result = msg["result"]
        text = result["content"][0]["text"] if result.get("content") else ""
        return tool_result(tool, text, bool(result.get("isError")))

    def close(self) -> None:
        try:
            if self._session_id:
                self._conn.request("DELETE", self.path, headers={"Mcp-Session-Id": self._session_id})
                self._conn.getresponse().read()
        except Exception:  # noqa: BLE001, S110 - best effort; the session expires on its own
            pass
        finally:
            self._conn.close()


def run_fast_session[T](
    url: str,
    tenant: str,
    agent_id: str,
    fn: Callable[[FastSession], Awaitable[T]],
    *,
    timeout: float = 5.0,
) -> T:
    """Open a session, run ``await fn(session)``, close it. Everything must finish within ``timeout`` seconds."""
    s = FastSession(url, tenant, agent_id, time.monotonic() + timeout)
    try:
        s.open()
        return asyncio.run(fn(s))
    except (ValueError, KeyError, IndexError) as exc:  # a malformed reply
        raise McpCallError(
            f"unexpected reply from the Plexus server: {type(exc).__name__}: {exc}"[:200]
        ) from exc
    finally:
        s.close()
