"""B0 / B1 unit tests: the discriminator key, the token set and the sequence guard (no DB, no embedder)."""

# ruff: noqa: E501 - long literal tables and prose lines

from __future__ import annotations

import pytest

from knewat.engram.dedup import (
    DedupSettings,
    features,
    jaccard,
    sequence_blocks,
    substitution_blocks,
)


def same_key(a: str, b: str) -> bool:
    return features(a).key == features(b).key


# -- B.1 failure list of docs/research/PRODUCT_FIXES_ANALYSIS.md: these must NOT share a discriminator key ----
HOSTILE = [
    ("The cache is enabled", "The cache is not enabled in staging"),
    ("Retries are enabled", "Retries are disabled for the orders queue"),
    ("Feature flag is on", "Feature flag is off for all users"),
    ("Latency must stay below 200 ms", "Latency must stay above 200 ms"),
    ("Retries at least 3", "Retries at most 3 times"),
    ("Two reviewers", "Three reviewers"),
    ("timeout is 5 minutes", "timeout is 5 hours"),
    ("Deploys are allowed", "Deploys are never allowed on Fridays"),
    ("The service is available", "The service is unavailable"),
    ("Cache is healthy", "Cache is not healthy"),
    ("The API is reachable", "The API is unreachable"),
    ("Writes are blocking", "Writes are non-blocking"),
    ("Build passes", "Build fails"),
    ("timeout is 30 seconds", "timeout is 30 minutes"),
    ("Pool size is 10", "Pool size is ten thousand"),
    ("All requests are logged", "Some requests are logged"),
    ("Send alerts to oncall", "Never send alerts to oncall"),
    ("The flag is true", "The flag is false"),
    ("Max retries is 5", "Min retries is 5"),
    ("version 1.2.3", "version 1.2.4"),
    ("memory limit is 1 GB", "memory limit is 1 TB"),
    ("Shards: 4", "Shards: four hundred"),
]

# -- true duplicates that the key must keep together (and the unit changes of the same quantity) ----------------
SAME = [
    ("Owns it.", "owns it"),
    ("timeout is 5 minutes", "timeout is 300 seconds"),
    ("timeout is 5 min", "timeout is 300 s"),
    ("Two reviewers must approve", "2 reviewers must approve"),
    ("deploys need two reviewers", "two reviewers must approve every production deploy"),
    ("Retries are not enabled", "Retries aren't enabled"),
    ("The service is unavailable", "The service is not available"),
    ("Pool size is twenty five", "Pool size is 25"),
    ("Response time under 200 ms", "Response time under 0.2 seconds"),
    ("Disk quota 1 KiB", "Disk quota 1 kib"),
]


@pytest.mark.parametrize(("a", "b"), HOSTILE)
def test_hostile_pairs_have_different_keys(a, b):
    assert not same_key(a, b), (a, b, features(a).key, features(b).key)


@pytest.mark.parametrize(("a", "b"), SAME)
def test_true_duplicates_keep_equal_keys(a, b):
    assert same_key(a, b), (a, b, features(a).key, features(b).key)


def test_units_are_normalised_to_a_base_unit():
    assert features("5 minutes").key == features("300 seconds").key == features("5 min").key
    assert features("5 minutes").key != features("5 hours").key
    assert features("1 GB").key == features("1000 MB").key
    assert features("1 GB").key != features("1 GiB").key  # decimal and binary stay apart
    assert features("1 GiB").key == features("1024 MiB").key
    assert features("1.5 hours").key == features("90 minutes").key
    assert features("50%").key == features("50 percent").key


def test_number_words_become_numbers():
    assert features("two reviewers").key == features("2 reviewers").key
    assert features("twenty five").key == features("25").key
    assert features("two hundred").key == features("200").key
    assert features("first responder").key == features("1st responder").key
    assert features("half").key == features("0.5").key


def test_versions_and_plain_numbers_stay_exact():
    assert features("v1.2.3").key != features("v1.2.4").key
    assert features("python 3.10").key != features("python 3.1").key
    assert features("port 8080").key == features("port 8,080").key


def test_prefix_negation_does_not_fire_on_ordinary_words():
    for w in (
        "unit",
        "union",
        "until",
        "display",
        "disk",
        "distribute",
        "unique",
        "uniform",
        "nonce",
        "undo",
    ):
        assert "neg" not in features(f"the {w} of work").key.split(), w


def test_flipped_antonym_by_prefix():
    assert features("lock held").key != features("unlock held").key
    assert features("enabled").key != features("disabled").key


def test_sequence_guard_blocks_swapped_directions():
    a, b = features("Service A calls B"), features("Service B calls A")
    assert a.key == b.key
    assert sequence_blocks(a, b)
    a, b = features("migrates from X to Y"), features("migrates to X from Y")
    assert sequence_blocks(a, b)
    a, b = features("owns it."), features("owns it")
    assert not sequence_blocks(a, b)
    a, b = (
        features("deploys need two reviewers"),
        features("two reviewers must approve every production deploy"),
    )
    assert not sequence_blocks(a, b)  # different token sets: nothing to guard


def test_jaccard_is_stopword_and_stem_free():
    a, b = features("on-call engineer is paged first"), features("first to be paged is whoever is on call")
    assert jaccard(a.tok, b.tok) >= 0.5
    assert jaccard([], []) == 0.0
    assert jaccard(["a"], ["b"]) == 0.0
    assert jaccard(features("Written in Go").tok, features("Written in Rust").tok) < 0.6
    assert jaccard(features("Hosted in eu-west").tok, features("Hosted in us-east").tok) < 0.6


def test_features_are_sorted_unique_tokens_and_a_string_key():
    f = features("The cache is not enabled in staging, staging!")
    assert f.tok == sorted(set(f.tok))
    assert isinstance(f.key, str) and isinstance(f.seq, list)
    assert f.key == features("staging the CACHE is   not enabled in staging").key


def test_settings_defaults_and_env_override():
    s = DedupSettings.from_env({})
    assert (s.jaccard, s.tier2_cos, s.maybe_cos, s.maybe_jaccard) == (0.6, 0.16, 0.20, 0.5)
    s = DedupSettings.from_env({"KNEWAT_DUP_JACCARD": "0.7", "KNEWAT_DUP_TIER2_COS": "0.12"})
    assert s.jaccard == 0.7 and s.tier2_cos == 0.12
    with pytest.raises(ValueError, match="KNEWAT_DUP_JACCARD"):
        DedupSettings.from_env({"KNEWAT_DUP_JACCARD": "1.5"})


def test_substitution_guard_blocks_a_one_word_change_but_not_a_paraphrase():
    for a, b in [
        ("Runs on Mondays", "Runs on Fridays"),
        ("Written in Go", "Written in Rust"),
        ("Exports the new orders to the warehouse", "Exports the old orders to the warehouse"),
        # the replacing word also occurs elsewhere in the sentence: a pure set difference misses this one
        (
            "When a request fails with a server error the client waits one second and retries",
            "When a request fails with a client error the client waits one second and retries",
        ),
    ]:
        fa, fb = features(a), features(b)
        assert substitution_blocks(fa, fb), (a, b)
    for a, b in [
        ("Owns it.", "Owns it"),
        ("deploys need two reviewers", "two reviewers must approve every production deploy"),
        ("PostgreSQL 16", "Postgres version 16"),
    ]:
        fa, fb = features(a), features(b)
        assert not (sequence_blocks(fa, fb) or substitution_blocks(fa, fb)), (a, b)
