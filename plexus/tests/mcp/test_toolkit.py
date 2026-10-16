"""The tool-definition pattern (``plexus.mcp.toolkit``).

Every tool is declared the same way, and nested argument objects refuse unknown keys. Pinned once here instead
of once per tool."""

from __future__ import annotations

import pytest

from mcp import Client
from plexus.mcp import lineage_tools, memory_tools, staleness_tools, tools_engram, tools_impact, tools_relay
from plexus.mcp.limits import StrictModel
from plexus.mcp.toolkit import ToolTable
from plexus.mcp.tools import register_engram_relay

TABLES = [
    tools_engram.ENGRAM_TOOLS,
    tools_relay.RELAY_TOOLS,
    lineage_tools.LINEAGE_TOOLS,
    staleness_tools.STALENESS_TOOLS,
    memory_tools.MEMORY_TOOLS,
    tools_impact.IMPACT_TOOLS,
]


def _strict_models() -> list[type[StrictModel]]:
    """Every argument model declared in the MCP modules (they all subclass StrictModel)."""
    out, todo = [], list(StrictModel.__subclasses__())
    while todo:
        cls = todo.pop()
        out.append(cls)
        todo.extend(cls.__subclasses__())
    return [c for c in out if c.__module__.startswith("plexus.mcp.")]


def test_argument_models_exist_and_forbid_unknown_keys():
    models = _strict_models()
    assert {m.__name__ for m in models} >= {"TaskSpec", "ArtifactSpec", "ChangeSpec"}
    for model in models:
        assert model.model_config.get("extra") == "forbid", model.__name__
        with pytest.raises(ValueError, match="unknown key"):
            model.model_validate({"definitely_not_a_field": 1})


async def test_every_nested_object_in_a_tool_schema_forbids_additional_properties(server):
    async with Client(server) as c:
        tools = (await c.list_tools()).tools
    nested = {name: d for t in tools for name, d in t.input_schema.get("$defs", {}).items()}
    assert set(nested) == {m.__name__ for m in _strict_models()}
    for name, schema in nested.items():
        assert schema["additionalProperties"] is False, name


def test_every_tool_declares_agent_id_and_step_and_a_unique_name():
    names = [d.name for table in TABLES for d in table]
    assert len(names) == len(set(names)) == 42
    for table in TABLES:
        for d in table:
            params = list(d.work.__annotations__)
            assert params[0] == "ts" and params[1] == "m" and params[2] == "agent_id", d.name
            assert "step" in params and "ctx" not in params, d.name


async def test_published_tools_are_exactly_the_tables(server):
    async with Client(server) as c:
        published = {t.name for t in (await c.list_tools()).tools}
    assert published == {d.name for table in TABLES for d in table}


def test_register_engram_relay_returns_names_in_definition_order():
    from plexus.mcp.server import PlexusServer

    mcp = PlexusServer("t")
    names = register_engram_relay(mcp, None)  # type: ignore[arg-type]  # the runtime is only used when a tool runs
    assert names == [d.name for t in (tools_engram.ENGRAM_TOOLS, tools_relay.RELAY_TOOLS) for d in t]


def test_a_tool_without_agent_id_or_step_is_rejected_at_definition_time():
    table = ToolTable()

    def no_step(ts, m, agent_id):
        raise AssertionError("never called")

    def bad_head(a, b, agent_id, step=None):
        raise AssertionError("never called")

    with pytest.raises(TypeError, match="agent_id and step"):
        table(no_step)
    with pytest.raises(TypeError, match=r"\(ts, m\)"):
        table(bad_head)
    assert list(table) == []


def test_requires_gates_a_tool_on_the_available_methods():
    table = ToolTable()

    @table.when("quarantine")
    def gated(ts, m, agent_id, step=None):
        raise AssertionError("never called")

    from plexus.mcp.server import PlexusServer

    mcp = PlexusServer("t")
    assert table.register(mcp, None, available={"why"}) == []  # type: ignore[arg-type]
    assert table.register(mcp, None, available={"quarantine"}) == ["gated"]  # type: ignore[arg-type]
    assert table.register(PlexusServer("t2"), None) == ["gated"]  # type: ignore[arg-type]


async def test_description_is_the_cleaned_docstring(server):
    """Published descriptions are dedented docstrings: no indentation carried over from the source file."""
    async with Client(server) as c:
        tools = (await c.list_tools()).tools
    for t in tools:
        desc = t.description or ""
        assert desc and desc == desc.strip(), t.name
        assert not any(ln.startswith("    ") for ln in desc.split("\n")), t.name
