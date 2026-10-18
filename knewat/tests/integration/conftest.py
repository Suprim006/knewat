from __future__ import annotations

import pytest

from knewat.embed import HashEmbedder
from knewat.engram import Engram


@pytest.fixture
def eng(client, graph) -> Engram:
    return Engram(client, graph, HashEmbedder())


@pytest.fixture
def glob(eng) -> str:
    return eng.create_scope("global", "global")


@pytest.fixture
def proj(eng, glob) -> str:
    return eng.create_scope("project", "acme", inherits=[glob])
