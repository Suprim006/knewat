"""Lineage tools register only when ``plexus.lineage`` exists, and only the methods it provides."""

from __future__ import annotations

import sys
import types

import pytest

from mcp import Client
from plexus.embed import HashEmbedder
from plexus.mcp.embedding import CheckedEmbedder
from plexus.mcp.lineage_tools import lineage_available
from plexus.mcp.runtime import Runtime
from plexus.mcp.server import build_server


class FakeLineage:
    def __init__(self, client, graph):
        self.graph = graph

    def why(self, node_id):
        return {"node": node_id, "paths": [["a", "b"]]}

    def as_of(self, subject, predicate, t, scope_id):
        return {"subject": subject, "t": t}


async def test_no_lineage_module_no_lineage_tools(server):
    if lineage_available():
        pytest.skip("real plexus.lineage is installed (covered by the orchestrator's post-merge run)")
    async with Client(server) as c:
        names = {t.name for t in (await c.list_tools()).tools}
    assert not names & {"why", "why_recalled", "who_knew", "knew_at", "as_of", "forget_source"}


async def test_lineage_tools_registered_from_available_methods(monkeypatch, client, tenant):
    mod = types.ModuleType("plexus.lineage")
    mod.Lineage = FakeLineage
    monkeypatch.setitem(sys.modules, "plexus.lineage", mod)
    rt = Runtime(client=client, embedder=HashEmbedder(), stdio_tenant=tenant)
    async with Client(build_server(rt)) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        assert {"why", "as_of"} <= names
        assert not names & {"who_knew", "forget_source", "knew_at", "why_recalled"}
        res = await c.call_tool("why", {"agent_id": "a", "node_id": "d1"})
        assert not res.is_error
        assert '"node": "d1"' in res.content[0].text


def test_embedder_guard_rejects_wrong_dimension():
    class Bad:
        dim = 384

        def embed(self, texts):
            return [[0.0] * 10 for _ in texts]

    with pytest.raises(ValueError, match="384"):
        CheckedEmbedder(Bad()).embed(["x"])
    assert len(CheckedEmbedder(HashEmbedder()).embed(["x"])[0]) == 384
