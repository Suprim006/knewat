"""Arm P answers every question with Cypher, and the answers equal the script-derived ground truth."""

from __future__ import annotations

import os

import pytest

from plexus.crucible.l2.plexus_answerer import QUERIES_ROOT, PlexusAnswerer
from plexus.crucible.l2.questions import build_questions, score
from plexus.crucible.l2.scenario import play
from plexus.graph.client import GraphClient
from plexus.graph.queries import QueryLibrary

DB_HOST = "127.0.0.1"
DB_PORT = int(os.environ.get("PLEXUS_TEST_DB_PORT", "6310"))


def test_every_query_file_loads_and_is_read_only():
    lib = QueryLibrary(QUERIES_ROOT)
    names = lib.names("l2/")
    assert len(names) >= 15
    for n in names:
        assert lib.get(n).mode == "ro", n


def test_every_op_has_a_cypher_answerer(tmp_path):
    from plexus.crucible.l2.questions import generate

    _, qs = generate(tmp_path)
    ops = {n[4:] for n in vars(PlexusAnswerer) if n.startswith("_op_")}
    assert {q.op for q in qs} <= ops


@pytest.mark.integration
def test_plexus_answers_match_ground_truth(opened):
    b = opened("P")
    led = play(b)
    qs = build_questions(led)
    client = GraphClient(host=DB_HOST, port=DB_PORT)
    try:
        ans = PlexusAnswerer(client, b.tenant)
        wrong = []
        for q in qs:
            got, meta = ans.answer(q)
            assert meta["statements"] >= 1
            ok, why = score(q, got)
            if not ok:
                wrong.append((q.id, q.text[:60], q.answer, got, why))
        assert not wrong, wrong
    finally:
        client.close()
