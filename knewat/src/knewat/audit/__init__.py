"""ToolCall audit: one ``ToolCall`` node per MCP tool call (feeds the View's flow timeline)."""

from knewat.audit.recorder import MAX_LINKS, record_tool_call

__all__ = ["MAX_LINKS", "record_tool_call"]
