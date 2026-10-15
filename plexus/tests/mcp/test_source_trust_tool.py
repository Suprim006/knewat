"""P7-int: the add_source tool accepts trust 'normal' | 'high' (and a legacy number, which means 'normal')."""

from __future__ import annotations

from mcp import Client

from .test_tool_coverage import err, ok, rows


async def test_add_source_tool_takes_normal_high_or_a_legacy_number(server, client, tenant):
    async with Client(server) as c:
        a = await ok(c, "add_source", agent_id="a", title="A", uri="https://x.example/a")
        b = await ok(c, "add_source", agent_id="a", title="B", uri="https://x.example/b", trust="high")
        d = await ok(c, "add_source", agent_id="a", title="D", uri="https://x.example/d", trust=0.3)
        assert "trust" in await err(
            c, "add_source", agent_id="a", title="E", uri="https://x.example/e", trust="meh"
        )
    got = dict(rows(client, tenant, "MATCH (s:Source) RETURN s.id, s.trust"))
    assert got == {a["source_id"]: "normal", b["source_id"]: "high", d["source_id"]: "normal"}
