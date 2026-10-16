"""P9-int: ``Entity.num_key`` is P9-c's discriminator key (numbers, quantities, number words, negation), not
just the numbers, so the vector path of ``resolve_entity`` cannot merge entities the dedup rules separate."""

from __future__ import annotations

import pytest

from plexus.embed import HashEmbedder
from plexus.engram import Engram
from plexus.engram.dedup import features


class SameVector(HashEmbedder):
    """Every text embeds to the same vector: the vector path always sees a perfect match, so only the
    ``num_key`` guard can keep two entities apart."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [super().embed(["entity"])[0] for _ in texts]


@pytest.fixture
def eng(client, graph) -> Engram:
    return Engram(client, graph, SameVector())


def _num_key(client, graph, entity_id: str) -> str:
    return (
        client.graph(graph)
        .ro_query("MATCH (e:Entity {id: $i}) RETURN e.num_key", {"i": entity_id})
        .result_set[0][0]
    )


def test_num_key_is_the_discriminator_key(eng, client, graph):
    e = eng.resolve_entity_ex("Auth Service two", "thing")
    assert _num_key(client, graph, e["id"]) == features("Auth Service two").key == "n:2"
    n = eng.resolve_entity_ex("not payment gateway", "thing")
    assert _num_key(client, graph, n["id"]) == features("not payment gateway").key == "neg"


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("auth-service-a", "auth-service-b"),
        ("payment gateway enabled", "payment gateway not enabled"),
        ("cache 5 minutes", "cache 5 hours"),
        ("Auth Service 2", "Auth Service 3"),
    ],
)
def test_the_vector_path_does_not_merge_entities_the_discriminator_separates(eng, a, b):
    first = eng.resolve_entity_ex(a, "thing")
    second = eng.resolve_entity_ex(b, "thing")
    assert first["id"] != second["id"], (a, b, second)
    assert second["created"] is True


def test_the_vector_path_still_merges_equal_keys(eng):
    first = eng.resolve_entity_ex("Payment Service", "thing")
    second = eng.resolve_entity_ex("payments service", "thing")  # same discriminator key, identical vector
    assert second["id"] == first["id"] and second["matched_by"] == "vector"
