"""P9-f: ``impact`` gives timestamps (bug 1) and never hides a cut list (bug 2).

Crucible L6-A found that (1) the facts came back without any time, so "the 5 earliest affected facts" could
not be answered, and (2) the MCP tool listed at most 200 ids with no sign that the list was cut, so "not in
the first 200" read as "not affected".
"""

from __future__ import annotations

import pytest

from knewat.lineage import Lineage

from .blast_p9f import build_blast


@pytest.fixture
def blast(client, graph):
    return build_blast(client, graph, n=600, levels=6)


def test_impact_records_carry_timestamps_and_can_be_ordered_by_time(client, graph, blast):
    lin = Lineage(client, graph)
    r = lin.impact("source", blast["source"], depth=12, max_detail=5, order="valid_from")
    f = r["facts"]
    assert f["order"] == "valid_from"
    assert f["ids"] == blast["facts"][:5]  # the 5 earliest, oldest first
    assert [x["id"] for x in f["records"]] == f["ids"]
    assert [x["valid_from"] for x in f["records"]] == [blast["at"][i] for i in f["ids"]]
    assert all(x["created_at"] == blast["at"][x["id"]] and x["status"] == "active" for x in f["records"])
    by_created = lin.impact("source", blast["source"], depth=12, max_detail=5, order="created_at")
    assert by_created["facts"]["ids"] == blast["facts"][:5]
    default = lin.impact("source", blast["source"], depth=12, max_detail=5)
    assert default["facts"]["order"] == "id" and default["facts"]["ids"] == sorted(blast["at"])[:5]
    with pytest.raises(ValueError):
        lin.impact("source", blast["source"], order="nope")


def test_impact_says_when_a_list_is_cut_and_pages_through_it(client, graph, blast):
    lin = Lineage(client, graph)
    first = lin.impact("source", blast["source"], depth=12, max_detail=200)
    f = first["facts"]
    assert f["total"] == 600 and len(f["ids"]) == 200
    assert f["ids_truncated"] is True and f["offset"] == 0 and f["next_offset"] == 200
    seen = list(f["ids"])
    nxt = f["next_offset"]
    while nxt is not None:
        page = lin.impact("source", blast["source"], depth=12, max_detail=200, offset=nxt)["facts"]
        seen += page["ids"]
        nxt = page["next_offset"]
    assert seen == sorted(blast["at"]) and page["ids_truncated"] is True  # the last page is not all of it
    # every other list says whether it was cut too
    small = lin.impact("source", blast["source"], depth=12, max_detail=1)
    assert small["readers"]["agents_truncated"] is (small["readers"]["agents_total"] > 1)
    for key in ("decisions", "tasks", "handoffs"):
        assert small[key]["ids_truncated"] is (small[key]["total"] > 1), key
    whole = lin.impact("source", blast["source"], depth=12, max_detail=5000)
    assert whole["facts"]["ids_truncated"] is False and whole["facts"]["next_offset"] is None


def test_impact_answers_membership_probes_beyond_the_listed_page(client, graph, blast):
    lin = Lineage(client, graph)
    last = sorted(blast["at"])[-1]  # not on the first page of 10
    r = lin.impact("source", blast["source"], depth=12, max_detail=10, probe_ids=[last, "not-a-fact"])
    assert last not in r["facts"]["ids"]
    assert r["facts"]["probes"] == {last: True, "not-a-fact": False}
