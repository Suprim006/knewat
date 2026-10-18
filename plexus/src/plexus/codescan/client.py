# ruff: noqa: E501  (long prose lines, as in mcp/ and cli.py)
"""A tiny client for the Plexus MCP server over streamable HTTP (``{url}/mcp/t/{tenant}``).

Used by the CLI and the hooks; it runs on the developer machine and only calls the MCP tools, exactly like an agent.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp import Client

DEFAULT_URL = "http://127.0.0.1:8765"
DEFAULT_AGENT = "code-hook"


class McpCallError(RuntimeError):
    """A tool call failed (the server's one-line message is the exception text)."""


def default_url() -> str:
    return os.environ.get("PLEXUS_URL") or DEFAULT_URL


def tenant_path(base: str, tenant: str) -> str:
    """``<base>/mcp/t/<tenant>``: the tenant's MCP endpoint below ``base`` (a URL, or just its path)."""
    return f"{base.rstrip('/')}/mcp/t/{tenant}"


def tool_arguments(agent_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """The arguments of a tool call: the caller's own, with ``agent_id`` filled in unless they set it."""
    return {"agent_id": agent_id, **args}


def tool_result(tool: str, text: str, is_error: bool) -> dict[str, Any]:
    """The JSON a tool call returned; a tool error becomes :class:`McpCallError` (the server's message)."""
    if is_error:
        raise McpCallError(text or f"{tool} failed")
    return json.loads(text)


class Session:
    """An open MCP session bound to one tenant; ``await s.call('tool', **args)`` returns the tool's JSON."""

    def __init__(self, client: Client, agent_id: str):
        self._c = client
        self.agent_id = agent_id

    async def call(self, tool: str, /, **args: Any) -> dict[str, Any]:
        res = await self._c.call_tool(tool, tool_arguments(self.agent_id, args))
        return tool_result(tool, res.content[0].text if res.content else "", res.is_error)


def run_session[T](
    url: str,
    tenant: str,
    agent_id: str,
    fn: Callable[[Session], Awaitable[T]],
    *,
    timeout: float = 10.0,
) -> T:
    """Open a session, run ``await fn(session)`` and close it; everything must finish within ``timeout`` seconds."""

    from mcp import Client  # imported here: it costs seconds, and the hooks never need it

    async def go() -> T:
        async with Client(tenant_path(url, tenant)) as c:
            return await fn(Session(c, agent_id))

    async def bounded() -> T:
        return await asyncio.wait_for(go(), timeout)

    try:
        return asyncio.run(bounded())
    except TimeoutError:
        raise McpCallError(f"no answer from {url} within {timeout:g}s") from None
    except McpCallError:
        raise
    except Exception as exc:  # connection refused, bad status, protocol error...
        inner = _leaves(exc)
        for e in inner:  # a tool error raised inside the client's task group arrives wrapped in a group
            if isinstance(e, McpCallError):
                raise e from None
        detail = "; ".join(str(e) or type(e).__name__ for e in inner)
        raise McpCallError(f"cannot reach Plexus at {url}: {detail[:200]}") from exc


def _leaves(exc: BaseException) -> list[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for e in exc.exceptions for leaf in _leaves(e)]
    return [exc]
