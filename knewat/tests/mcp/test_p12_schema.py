"""P12 token fix: the compact published tool schemas.

The L8 token breakdown (``plexus.crucible.l8.token_breakdown``) found the tool list, re-read on every API
call, to be the largest single cost of the P arm. These tests pin what the compact schema drops and what
it must keep.
"""

from __future__ import annotations

import json

from mcp import Client
from plexus.mcp.server import compact_schema


def test_compact_schema_drops_boilerplate_only():
    full = {
        "title": "recallArguments",
        "type": "object",
        "required": ["agent_id", "query"],
        "properties": {
            "agent_id": {
                "title": "Agent Id",
                "type": "string",
                "minLength": 1,
                "maxLength": 128,
                "description": "d",
            },
            "title": {"title": "Title", "type": "string", "maxLength": 2000},  # a parameter NAMED title stays
            "k": {"title": "K", "type": "integer", "minimum": 1, "maximum": 50, "default": 20},
            "step": {
                "anyOf": [{"type": "integer", "minimum": 1, "maximum": 2**31 - 1}, {"type": "null"}],
                "default": None,
                "title": "Step",
            },
            "audit": {
                "anyOf": [{"enum": ["light", "full"], "type": "string"}, {"type": "null"}],
                "default": None,
            },
            "n": {"type": "integer", "minimum": 0, "maximum": 9_999_999_999_999},
        },
        "$defs": {
            "A": {
                "title": "A",
                "type": "object",
                "additionalProperties": False,
                "properties": {"uri": {"type": "string", "maxLength": 2000}},
            }
        },
    }
    assert compact_schema(full) == {
        "type": "object",
        "required": ["agent_id", "query"],
        "properties": {
            "agent_id": {"type": "string", "description": "d"},
            "title": {"type": "string"},
            "k": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
            "step": {"type": "integer", "minimum": 1},
            "audit": {"enum": ["light", "full"], "type": "string"},
            "n": {"type": "integer"},
        },
        "$defs": {
            "A": {"type": "object", "additionalProperties": False, "properties": {"uri": {"type": "string"}}}
        },
    }


async def test_published_schemas_are_compact_and_validation_still_holds(server):
    async with Client(server) as c:
        tools = (await c.list_tools()).tools
        dumped = json.dumps([t.input_schema for t in tools])

        def keys(s, under_props=False):
            if isinstance(s, dict):
                for k, v in s.items():
                    if not under_props:
                        yield k
                    yield from keys(v, k in ("properties", "$defs"))
            elif isinstance(s, list):
                for x in s:
                    yield from keys(x)

        used = {k for t in tools for k in keys(t.input_schema)}
        assert not {"title", "maxLength", "minLength", "maxItems"} & used, used
        assert '{"type": "null"}]' not in dumped.replace(
            '{"maximum": 1.0, "type": "number"}, {"type": "null"}]', ""
        )
        assert all(t.output_schema is None for t in tools)
        # a dropped bound is still enforced by the server's own argument model
        res = await c.call_tool("recall", {"agent_id": "x" * 200, "query": "q"})
        assert res.is_error and "agent_id" in res.content[0].text
        res = await c.call_tool("recall", {"agent_id": "a", "query": "q", "k": 51})
        assert res.is_error and "k" in res.content[0].text
