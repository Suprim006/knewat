"""Shared fixtures. Integration tests use a throwaway graph per test on KNEWAT_TEST_DB_PORT (default 6310)."""

from __future__ import annotations

import os

import pytest
from redis.exceptions import RedisError

from knewat.graph.client import GraphClient
from knewat.graph.queries import QueryLibrary
from knewat.graph.schema import apply_schema
from knewat.graph.tenancy import test_graph_name

TEST_DB_HOST = "127.0.0.1"  # "localhost" tries ::1 first on Windows+Docker (+2 s per connection)
TEST_DB_PORT = int(os.environ.get("KNEWAT_TEST_DB_PORT", "6310"))


def pytest_collection_modifyitems(items):
    """Anything that uses a DB fixture is an integration test."""
    for item in items:
        if {"client", "graph", "empty_graph", "aclient"} & set(item.fixturenames):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def library() -> QueryLibrary:
    return QueryLibrary()


@pytest.fixture(scope="session")
def client(library):
    c = GraphClient(host=TEST_DB_HOST, port=TEST_DB_PORT, password="", library=library)
    try:
        c.ping()
    except RedisError as exc:  # fail loudly: a silent skip would hide a missing DB in the gate
        pytest.fail(
            f"FalkorDB not reachable on {TEST_DB_HOST}:{TEST_DB_PORT} ({exc}). "
            "Start one with scripts/agent_db.sh <slot> and pass KNEWAT_TEST_DB_PORT=63<slot> inline.",
            pytrace=False,
        )
    yield c
    c.close()


@pytest.fixture
def empty_graph(client):
    """A fresh ``test_<uuid>`` graph name with nothing applied; dropped in teardown even on failure."""
    name = test_graph_name()
    try:
        yield name
    finally:
        client.delete_graph(name)


@pytest.fixture
def graph(client, empty_graph):
    """A fresh ``test_<uuid>`` graph with the full schema applied."""
    apply_schema(client, empty_graph)
    return empty_graph
