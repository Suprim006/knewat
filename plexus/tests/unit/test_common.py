"""plexus.common: the helpers every service shares."""

import time

import pytest

from plexus import common
from plexus.engram import OPEN as ENGRAM_OPEN
from plexus.engram import normalize as engram_normalize


def test_open_and_normalize_are_the_same_objects_everywhere():
    assert common.OPEN == 9_999_999_999_999
    assert ENGRAM_OPEN == common.OPEN
    assert engram_normalize is common.normalize


def test_now_ms_is_epoch_milliseconds_and_new_id_is_a_uuid_string():
    assert abs(common.now_ms() - time.time() * 1000) < 1000
    a, b = common.new_id(), common.new_id()
    assert a != b and len(a) == 36 and a.count("-") == 4


def test_unique_keeps_first_occurrence_order():
    assert common.unique(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]
    assert common.unique(None) == [] and common.unique(()) == []


@pytest.mark.parametrize("bad", [0, -1, 11])
def test_check_between_rejects_outside_one_to_maximum(bad):
    with pytest.raises(ValueError, match=r"^limit must be between 1 and 10$"):
        common.check_between("limit", bad, 10)


def test_check_between_accepts_the_bounds():
    common.check_between("limit", 1, 10)
    common.check_between("limit", 10, 10)
