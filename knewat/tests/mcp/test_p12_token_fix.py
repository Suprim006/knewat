"""P12 token fix: recall's compact hits.

The L8 token breakdown (``knewat.crucible.l8.token_breakdown``) found recall's full hits to be ~12% of the
P arm's tokens, 42% of each hit the provenance path no agent used. These tests pin what the compact hit
must keep.
"""

from __future__ import annotations

import json

import pytest

from knewat.common import OPEN
from knewat.mcp.tools_engram import compact_hit
from mcp import Client


async def ok(c: Client, tool: str, /, **args) -> dict:
    res = await c.call_tool(tool, args)
    assert not res.is_error, res.content[0].text
    return json.loads(res.content[0].text)


FULL_HIT = {
    "fact_id": "f1", "text": "Acme API version: v2", "score": 0.5,
    "path": [{"rel": "ABOUT", "label": "Entity", "id": "e1", "name": "Acme API"},
             {"rel": "IN_SCOPE", "label": "Scope", "id": "s1"},
             {"rel": "DERIVED_FROM", "label": "Source", "id": "src1"},
             {"rel": "ASSERTED_BY", "label": "Agent", "id": "researcher"}],
    "entity": "Acme API", "predicate": "version", "value": "v2", "status": "active",
    "valid_from": 1, "valid_to": OPEN, "via": None, "surprise": 0.3, "activation": -0.9, "protected": False,
    "maybe_duplicate_of": [], "verify_state": "verified", "suspect_since": 0, "suspect_reason": None,
}  # fmt: skip


def test_compact_hit_keeps_the_answer_and_drops_defaults():
    got = compact_hit(FULL_HIT)
    assert got == {"fact_id": "f1", "entity": "Acme API", "predicate": "version", "value": "v2",
                   "valid_from": 1, "score": 0.5, "by": "researcher"}  # fmt: skip


def test_compact_hit_keeps_every_non_default_flag():
    h = {
        **FULL_HIT,
        "status": "superseded",
        "valid_to": 5,
        "via": "f0",
        "protected": True,
        "maybe_duplicate_of": ["f9"],
        "verify_state": "suspect",
        "suspect_since": 4,
        "suspect_reason": "changed",
        "hop": 1,
        "relation_path": ["CALLS"],
    }
    got = compact_hit(h)
    for k in ("status", "valid_to", "via", "protected", "maybe_duplicate_of", "verify_state", "suspect_since",
              "suspect_reason", "hop", "relation_path"):  # fmt: skip
        assert got[k] == h[k], k
    assert not {"text", "path", "surprise", "activation"} & set(got)


@pytest.mark.parametrize("detail", ["compact", "full"])
async def test_recall_detail_returns_the_same_facts_in_the_same_order(server, detail):
    async with Client(server) as c:
        for n in range(1, 13):
            await ok(c, "assert_fact", agent_id="p", subject=f"Acme API S{n:02d}", predicate="api_version",
                     value=f"v{n}")  # fmt: skip
        full = await ok(c, "recall", agent_id="r", query="Acme API version", detail="full")
        got = await ok(c, "recall", agent_id="r", query="Acme API version", detail=detail)
    assert [f["fact_id"] for f in got["facts"]] == [f["fact_id"] for f in full["facts"]]
    assert [(f["entity"], f["predicate"], f["value"]) for f in got["facts"]] == [
        (f["entity"], f["predicate"], f["value"]) for f in full["facts"]
    ]
    assert got["count"] == full["count"] and got["truncated"] == full["truncated"]
    if detail == "compact":
        assert len(json.dumps(got)) < 0.5 * len(json.dumps(full))
        assert all(f["by"] == "p" for f in got["facts"])
