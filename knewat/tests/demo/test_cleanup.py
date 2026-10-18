"""D5: the demo/api test fixtures clean up after hard-killed runs and survive a failing delete."""

from __future__ import annotations

import uuid

import pytest

from knewat.graph.tenancy import graph_name

from ..api.conftest import drop_graphs as api_drop
from ..api.conftest import sweep_stale_graphs as api_sweep
from .conftest import drop_graphs as demo_drop
from .conftest import sweep_stale_graphs as demo_sweep


def _make(client, name: str) -> str:
    client.graph(name).query("CREATE (:Probe {id: $i})", {"i": uuid.uuid4().hex})
    return name


def _exists(client, name: str) -> bool:
    return name in client.db.list_graphs()


@pytest.mark.parametrize(
    ("sweep", "tenant_prefix"), [(demo_sweep, "demot_"), (api_sweep, "apit_")], ids=["demo", "api"]
)
def test_sweep_drops_leaked_tenants_of_its_own_prefix_only(client, sweep, tenant_prefix):
    leaked = _make(client, graph_name(f"{tenant_prefix}{uuid.uuid4().hex[:10]}"))
    other = _make(client, graph_name(f"keepme_{uuid.uuid4().hex[:10]}"))
    try:
        sweep(client)
        assert not _exists(client, leaked)
        assert _exists(client, other)
    finally:
        client.delete_graph(leaked)
        client.delete_graph(other)


def test_sweep_can_be_switched_off(client, monkeypatch):
    leaked = _make(client, graph_name(f"demot_{uuid.uuid4().hex[:10]}"))
    try:
        monkeypatch.setenv("KNEWAT_TEST_KEEP_STALE", "1")
        demo_sweep(client)
        assert _exists(client, leaked)
    finally:
        client.delete_graph(leaked)


class _FlakyClient:
    def __init__(self, bad: str):
        self.bad = bad
        self.deleted: list[str] = []

    def delete_graph(self, name: str) -> None:
        if name == self.bad:
            raise RuntimeError(f"cannot drop {name}")
        self.deleted.append(name)


@pytest.mark.parametrize("drop", [demo_drop, api_drop], ids=["demo", "api"])
def test_one_failing_delete_does_not_leak_the_rest(drop):
    fake = _FlakyClient(graph_name("t2"))
    with pytest.raises(RuntimeError, match="cannot drop knewat_t_t2"):
        drop(fake, ["t1", "t2", "t3"])
    assert fake.deleted == [graph_name("t1"), graph_name("t3")]
