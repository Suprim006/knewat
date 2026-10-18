"""Fixtures for the Crucible tests: one throw-away tenant per test, for every arm."""

from __future__ import annotations

import os
import uuid

import pytest

from knewat.crucible.api import BackendSpec
from knewat.crucible.backends import open_backend
from knewat.graph.client import GraphClient
from knewat.graph.tenancy import graph_name

DB_HOST = "127.0.0.1"
DB_PORT = int(os.environ.get("KNEWAT_TEST_DB_PORT", "6310"))

ARMS = [
    "B0",
    "B1",
    pytest.param("B2", marks=pytest.mark.slow),
    pytest.param("P", marks=pytest.mark.integration),
    pytest.param("P-mcp", marks=pytest.mark.integration),
]


def new_tenant() -> str:
    return "crt_" + uuid.uuid4().hex[:12]


@pytest.fixture(scope="session")
def embedder_kind() -> str:
    return os.environ.get("CRUCIBLE_TEST_EMBEDDER", "hash")


@pytest.fixture
def make_spec(tmp_path, embedder_kind):
    def make(arm: str, tenant: str | None = None) -> BackendSpec:
        return BackendSpec(
            arm=arm,
            tenant=tenant if tenant is not None else new_tenant(),
            root=str(tmp_path / "files"),
            host=DB_HOST,
            port=DB_PORT,
            embedder=embedder_kind,
        )

    return make


@pytest.fixture
def opened(make_spec):
    """Factory that opens backends and drops their graphs / closes them at teardown."""
    made = []

    def open_(arm: str, tenant: str | None = None):
        b = open_backend(make_spec(arm, tenant))
        made.append(b)
        return b

    yield open_
    cleaner = None
    for b in made:
        try:
            b.close()
        except Exception:  # noqa: BLE001
            pass
        if b.name.startswith("P"):
            cleaner = cleaner or GraphClient(host=DB_HOST, port=DB_PORT)
            cleaner.delete_graph(graph_name(b.tenant))
    if cleaner is not None:
        cleaner.close()


@pytest.fixture(params=ARMS)
def arm(request) -> str:
    return request.param


@pytest.fixture
def backend(arm, opened):
    return opened(arm)
