"""Engram + Relay MCP tools: the public ``register_engram_relay`` entry point.

The tools themselves live in :mod:`plexus.mcp.tools_engram` and :mod:`plexus.mcp.tools_relay`; the pattern that turns
a flat work function into a published tool is :mod:`plexus.mcp.toolkit`.
"""

from mcp.server.mcpserver import MCPServer

from plexus.mcp.runtime import Runtime
from plexus.mcp.tools_engram import ENGRAM_TOOLS, Role
from plexus.mcp.tools_relay import MAX_TASKS, RELAY_TOOLS, ArtifactSpec, TaskSpec

__all__ = ["MAX_TASKS", "ArtifactSpec", "Role", "TaskSpec", "register_engram_relay"]


def register_engram_relay(mcp: MCPServer, rt: Runtime) -> list[str]:
    """Register the Engram and Relay tools on ``mcp``; returns their names."""
    return [*ENGRAM_TOOLS.register(mcp, rt), *RELAY_TOOLS.register(mcp, rt)]
