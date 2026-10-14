from __future__ import annotations

from plexus.engram.service import _jaccard, _tokens, fact_text, normalize


def test_normalize():
    assert normalize("  Acme   NOTES\tAPI ") == "acme notes api"
    assert normalize("STRASSE") == normalize("strasse")


def test_tokens_and_jaccard():
    assert _tokens("Acme-Notes_API v2!") == ["acme", "notes", "api", "v2"]
    assert _jaccard({"a", "b"}, {"b", "c"}) == 1 / 3
    assert _jaccard(set(), set()) == 0.0


def test_fact_text():
    assert fact_text("Acme", "database", "PostgreSQL") == "Acme database: PostgreSQL"


def test_every_engram_query_loads_and_modes():
    from plexus.graph.queries import QueryLibrary

    lib = QueryLibrary()
    names = lib.names("engram/")
    assert {"engram/assert_fact", "engram/recall", "engram/remember_episode"} <= set(names)
    ro = {n for n in names if lib.get(n).mode == "ro"}
    assert ro == {
        "engram/recall",
        "engram/fact_history",
        "engram/best_procedure",
        "engram/find_entity_exact",
        "engram/find_entity_fulltext",
        "engram/find_entity_vector",
    }
    # R: one statement per operation
    assert all(len(lib.get(n).statements) == 1 for n in names)
