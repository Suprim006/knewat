"""P9-f: ``impact`` gives the time of every listed fact and can list the earliest first.

Crucible L6-A found that the facts came back without any time, so "the 5 earliest affected facts" could not be
answered by the product (strict 0/24 by construction).
"""

from __future__ import annotations

import pytest

from plexus.lineage import Lineage

from .blast import build_blast


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
