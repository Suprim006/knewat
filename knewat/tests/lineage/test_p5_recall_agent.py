"""P5-fix Q8: a rejected record_recall writes nothing, not even the Agent."""

from __future__ import annotations

import pytest

from knewat.lineage import UnknownStep

from .conftest import cypher


def _agents(client, graph):
    return cypher(client, graph, "MATCH (a:Agent) RETURN count(a)")[0][0]


def _recalls(client, graph):
    return cypher(client, graph, "MATCH (r:Recall) RETURN count(r)")[0][0]


def test_q8_unknown_fact_creates_no_agent(world, lin, client, graph):
    before = (_agents(client, graph), _recalls(client, graph))
    with pytest.raises(UnknownStep):
        lin.record_recall(
            "brand-new-agent", world.p1, "q", world.proj, 3, [{"fact_id": "no-such-fact"}], now=9000
        )
    assert (_agents(client, graph), _recalls(client, graph)) == before


def test_q8_unknown_step_creates_no_agent(world, lin, client, graph):
    before = _agents(client, graph)
    with pytest.raises(UnknownStep):
        lin.record_recall(
            "brand-new-agent", "no-such-step", "q", world.proj, 3, [{"fact_id": world.db1}], now=9000
        )
    assert _agents(client, graph) == before


def test_q8_accepted_record_recall_still_creates_the_agent(world, lin, client, graph):
    before = _agents(client, graph)
    step = lin.record_step("brand-new-agent", 1, at=9000)
    lin.record_recall("brand-new-agent", step, "q", world.proj, 3, [{"fact_id": world.db2}], now=9001)
    assert _agents(client, graph) == before + 1
    assert _recalls(client, graph) == 4
