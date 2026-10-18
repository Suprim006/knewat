from __future__ import annotations

from plexus.codescan.hashing import hash_bytes, python_symbols

SRC = '''\
import os


def add(a, b):
    return a + b


class Pay:
    """A payer."""

    LIMIT = 3

    def create(self, amount):
        return amount * 2

    @property
    def rate(self):
        return 1

    @rate.setter
    def rate(self, v):
        self._r = v


async def later():
    pass
'''


def _by_name(src):
    syms = python_symbols(src)
    assert syms is not None
    return {s.name: s for s in syms}


def test_hash_ignores_line_endings():
    assert hash_bytes(b"one\r\ntwo\r\n") == hash_bytes(b"one\ntwo\n")
    assert hash_bytes(b"one\ntwo") != hash_bytes(b"one\ntwo\n")


def test_symbols_are_functions_classes_and_methods_with_dotted_names():
    syms = _by_name(SRC)
    assert list(syms) == ["add", "Pay", "Pay.create", "Pay.rate", "later"]
    assert syms["add"].kind == "function" and syms["Pay"].kind == "class"
    assert syms["Pay.create"].kind == "function" and syms["later"].kind == "function"


def test_moving_a_function_does_not_change_its_hash():
    moved = (
        SRC.replace("def add(a, b):\n    return a + b\n\n\n", "") + "\n\ndef add(a, b):\n    return a + b\n"
    )
    a, b = _by_name(SRC), _by_name(moved)
    assert a["add"].hash == b["add"].hash
    assert a["Pay"].hash == b["Pay"].hash and a["later"].hash == b["later"].hash


def test_editing_a_body_changes_that_symbol_and_its_class_only():
    edited = SRC.replace("return amount * 2", "return amount * 3")
    a, b = _by_name(SRC), _by_name(edited)
    assert a["Pay.create"].hash != b["Pay.create"].hash
    assert a["Pay"].hash != b["Pay"].hash  # the class contains the method
    for same in ("add", "Pay.rate", "later"):
        assert a[same].hash == b[same].hash


def test_renaming_a_function_removes_the_old_symbol_and_adds_a_new_one():
    renamed = SRC.replace("def add(a, b)", "def plus(a, b)")
    a, b = _by_name(SRC), _by_name(renamed)
    assert "add" in a and "add" not in b and "plus" in b
    assert a["add"].hash != b["plus"].hash  # the name is part of the definition


def test_crlf_and_trailing_whitespace_do_not_change_hashes():
    crlf = SRC.replace("\n", "\r\n")
    padded = SRC.replace("return a + b", "return a + b   ")
    base = _by_name(SRC)
    assert {n: s.hash for n, s in _by_name(crlf).items()} == {n: s.hash for n, s in base.items()}
    assert _by_name(padded)["add"].hash == base["add"].hash


def test_nested_definitions_are_not_symbols_and_blank_lines_do_not_matter():
    wrapped = "if True:\n" + "".join("    " + ln if ln.strip() else ln for ln in SRC.splitlines(True))
    # nested in `if`, so the symbols are not top level: nothing is found, but the parse works
    assert python_symbols(wrapped) == []
    flat = _by_name(SRC)
    assert (
        flat["Pay.create"].hash
        == _by_name(SRC.replace("\n\n\nclass Pay", "\n\nclass Pay"))["Pay.create"].hash
    )


def test_decorators_are_part_of_the_definition():
    a = _by_name("@cache\ndef f():\n    return 1\n")["f"].hash
    b = _by_name("@lru_cache\ndef f():\n    return 1\n")["f"].hash
    c = _by_name("def f():\n    return 1\n")["f"].hash
    assert len({a, b, c}) == 3


def test_a_property_and_its_setter_share_one_symbol():
    syms = _by_name(SRC)
    edited = _by_name(SRC.replace("self._r = v", "self._r = v + 1"))
    assert syms["Pay.rate"].hash != edited["Pay.rate"].hash


def test_unparseable_source_gives_none_not_an_exception():
    assert python_symbols("def broken(:\n") is None
    assert python_symbols(b"\xff\xfe\x00") is None
    assert python_symbols("") == []
