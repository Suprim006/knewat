import re

import pytest

from knewat.graph.tenancy import graph_name, test_graph_name


@pytest.mark.parametrize("tenant", ["acme", "a", "t_1", "0", "a" * 48, "acme_notes_2026"])
def test_graph_name_valid(tenant):
    assert graph_name(tenant) == f"knewat_t_{tenant}"


@pytest.mark.parametrize(
    "tenant",
    ["", "A", "Acme", "a-b", "a b", "a.b", "a/b", "a" * 49, "acme\n", " acme", "é", "a;b", "knewat_t_x\x00"],
)
def test_graph_name_invalid(tenant):
    with pytest.raises(ValueError):
        graph_name(tenant)


@pytest.mark.parametrize("tenant", [None, 1, b"acme"])
def test_graph_name_rejects_non_str(tenant):
    with pytest.raises(ValueError):
        graph_name(tenant)  # type: ignore[arg-type]


def test_test_graph_name_shape_and_unique():
    a, b = test_graph_name(), test_graph_name()
    assert re.fullmatch(r"test_[0-9a-f]{32}", a)
    assert a != b
