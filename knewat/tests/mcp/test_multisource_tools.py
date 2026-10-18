"""P13 (trial 8) at the MCP surface: source_ids, corroborated / unlinked in the retraction results,
and a manifest that grows by a handful of words, not a paragraph."""

from __future__ import annotations

import json

import pytest

from knewat.crucible.l8.manifest_size import measure
from mcp import Client

from .test_lineage_integration import call, call_err, rows

CORE_CHARS_BEFORE = 30_182  # `manifest_size --toolset core` at integ 1f9a8fa (before P13)
FULL_CHARS_BEFORE = 47_843
BUDGET = 450  # characters the P13 tool-surface change may add to either list


async def _two_sources(c: Client) -> tuple[str, str]:
    memo = await call(c, "add_source", agent_id="a", title="memo", uri="urn:memo")
    spec = await call(c, "add_source", agent_id="a", title="spec", uri="urn:spec")
    return memo["source_id"], spec["source_id"]


async def _fact(c: Client, subject: str, value: str, **kw) -> dict:
    return await call(c, "assert_fact", agent_id="a", subject=subject, predicate="rule", value=value, **kw)


async def test_assert_fact_takes_source_ids_and_a_duplicate_reports_sources_added(client, tenant, server):
    async with Client(server) as c:
        memo, spec = await _two_sources(c)
        r = await _fact(c, "C1", "audit log", source_ids=[memo, spec])
        assert "sources_added" not in r
        linked = rows(
            client, tenant, "MATCH (:Fact {id: $f})-[:DERIVED_FROM]->(s:Source) RETURN s.id", f=r["fact_id"]
        )
        assert sorted(x[0] for x in linked) == sorted([memo, spec])
        third = await call(c, "add_source", agent_id="a", title="third", uri="urn:third")
        again = await _fact(c, "C1", "audit log", source_ids=[spec, third["source_id"]])
        assert again["duplicate_of"] == r["fact_id"] and again["sources_added"] == [third["source_id"]]


async def test_assert_fact_rejects_an_unknown_source_id(server):
    async with Client(server) as c:
        memo, _ = await _two_sources(c)
        err = await call_err(
            c,
            "assert_fact",
            agent_id="a",
            subject="C1",
            predicate="rule",
            value="x",
            source_ids=[memo, "nope"],
        )
        assert "nope" in err and "source" in err.lower()


async def test_assert_fact_source_ids_are_capped_at_twenty(server):
    async with Client(server) as c:
        err = await call_err(
            c, "assert_fact", agent_id="a", subject="C1", predicate="rule", value="x",
            source_ids=[f"s{i}" for i in range(21)],
        )  # fmt: skip
        assert "20" in err or "too_long" in err or "at most" in err.lower()


async def test_quarantine_and_forget_results_carry_corroborated_and_unlinked_only_when_there_are_any(server):
    async with Client(server) as c:
        memo, spec = await _two_sources(c)
        c1 = await _fact(c, "C1", "audit log", source_ids=[memo, spec])
        c2 = await _fact(c, "C2", "retention", source_id=memo)
        q = (await call(c, "quarantine_source", agent_id="a", source_id=memo))["quarantined"]
        assert q["fact_ids"] == [c2["fact_id"]]
        assert (
            q["corroborated"] == [{"fact_id": c1["fact_id"], "other_sources": [spec]}]
            and q["corroborated_total"] == 1
        )
        f = (await call(c, "forget_source", agent_id="a", source_id=memo))["forgotten"]
        assert (
            f["unlinked"] == [{"fact_id": c1["fact_id"], "other_sources": [spec]}]
            and f["unlinked_total"] == 1
        )
        only = await _fact(c, "P1", "sso", source_id=spec)
        q2 = (await call(c, "quarantine_source", agent_id="a", source_id=spec))["quarantined"]
        assert only["fact_id"] in q2["fact_ids"]
        assert "corroborated" not in q2 and "corroborated_total" not in q2  # nothing to say: nothing sent
        f2 = (await call(c, "forget_source", agent_id="a", source_id=spec))["forgotten"]
        assert "unlinked" not in f2 and "unlinked_total" not in f2


async def test_recall_stays_compact_and_full_lists_every_source(server):
    async with Client(server) as c:
        memo, spec = await _two_sources(c)
        c1 = await _fact(c, "C1", "audit log required", source_ids=[memo, spec])
        compact = (await call(c, "recall", agent_id="a", query="C1 rule"))["facts"]
        hit = next(h for h in compact if h["fact_id"] == c1["fact_id"])
        assert "path" not in hit and not any("urn:" in json.dumps(v) for v in hit.values())  # token budget
        full = (await call(c, "recall", agent_id="a", query="C1 rule", detail="full"))["facts"]
        path = next(h for h in full if h["fact_id"] == c1["fact_id"])["path"]
        assert sorted(p["id"] for p in path if p["rel"] == "DERIVED_FROM") == sorted([memo, spec])


async def test_why_names_every_source(server):
    async with Client(server) as c:
        memo, spec = await _two_sources(c)
        c1 = await _fact(c, "C1", "audit log", source_ids=[memo, spec])
        w = await call(c, "why", agent_id="a", node_id=c1["fact_id"])
        text = json.dumps(w)
        assert memo in text and spec in text


async def test_tool_descriptions_say_when_to_use_them(server):
    async with Client(server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
    assert "source_ids" in (tools["assert_fact"].description or "")
    for name in ("quarantine_source", "forget_source"):
        d = tools[name].description or ""
        assert "wrong" in d and "withdrawn" in d and "void" in d, name
        assert "another source" in d or "other source" in d, name
    assert "source_ids" in tools["assert_fact"].input_schema["properties"]


@pytest.mark.parametrize(("toolset", "before"), [("core", CORE_CHARS_BEFORE), ("full", FULL_CHARS_BEFORE)])
async def test_the_manifest_grew_by_less_than_the_budget(toolset, before):
    got = (await measure(toolset))["total_chars"]
    assert got - before <= BUDGET, f"{toolset}: +{got - before} chars"
