"""Diamond-DAG fixtures for the P9-b traversal tests and bench: many paths, few nodes.

``build_lineage``: a Source, then ``levels`` layers of ``width`` facts; every fact derives from ``fan_in``
facts of the layer below (layer 1 from the Source), so the number of DERIVED_FROM paths is about
``fan_in ** levels`` while the number of distinct facts is ``levels * width``. ``build_tasks``: root +
``levels`` layers of ``width`` tasks, each
depending on ``fan_in`` tasks of the layer below.

Built with raw parameterised Cypher (not the services) so a 12-level fixture takes milliseconds.
"""

from __future__ import annotations

from typing import Any

FAR = 9_999_999_999_999


class TimedClient:
    """Wraps a GraphClient; sums the server-side ``run_time_ms`` of every ``ro`` / ``rw`` call."""

    def __init__(self, inner):
        self._inner = inner
        self.server_ms = 0.0
        self.calls = 0

    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    def _timed(self, fn, *a, **kw):
        rows = fn(*a, **kw)
        self.server_ms += getattr(rows, "run_time_ms", 0.0)
        self.calls += 1
        return rows

    def ro(self, *a, **kw):
        return self._timed(self._inner.ro, *a, **kw)

    def rw(self, *a, **kw):
        return self._timed(self._inner.rw, *a, **kw)

    def reset(self) -> None:
        self.server_ms, self.calls = 0.0, 0


def _w(client, graph: str, q: str, **params) -> None:
    client.graph(graph).query(q, params)


def build_lineage(client, graph: str, *, levels: int = 12, width: int = 5, fan_in: int = 3) -> dict[str, Any]:
    """Return ``{source, layers: [[fact ids]], top, decision, agent}``; facts are active, valid forever."""
    _w(
        client,
        graph,
        "CREATE (:Source {id: 'src-d', uri: 'urn:diamond', kind: 'url', trust: 'normal', created_at: 1})",
    )
    _w(client, graph, "CREATE (:Agent {id: 'ag-d', name: 'ag-d', role: 'builder'})")
    layers = [[f"f{lv}-{j}" for j in range(width)] for lv in range(1, levels + 1)]
    facts = [{"id": fid, "lv": lv} for lv, layer in enumerate(layers, start=1) for fid in layer]
    _w(
        client,
        graph,
        "UNWIND $rows AS r CREATE (f:Fact {id: r.id, predicate: 'p', value: r.id, status: 'active', "
        "valid_from: 1, valid_to: $far, created_at: 1})",
        rows=facts,
        far=FAR,
    )
    edges = []
    for lv, layer in enumerate(layers):
        for j, fid in enumerate(layer):
            below = ["src-d"] if lv == 0 else [layers[lv - 1][(j + k) % width] for k in range(fan_in)]
            edges += [{"f": fid, "t": t} for t in below]
    _w(
        client,
        graph,
        "UNWIND $e AS x MATCH (a:Fact {id: x.f}) MATCH (b {id: x.t}) CREATE (a)-[:DERIVED_FROM]->(b)",
        e=edges,
    )
    top = layers[-1][0]
    _w(
        client,
        graph,
        "UNWIND $f AS fid MATCH (f:Fact {id: fid}) MATCH (a:Agent {id: 'ag-d'}) "
        "CREATE (f)-[:ASSERTED_BY]->(a)",
        f=[f["id"] for f in facts],
    )
    _w(
        client,
        graph,
        "MATCH (a:Agent {id: 'ag-d'}) MATCH (f:Fact {id: $top}) "
        "CREATE (d:Decision {id: 'dec-d', summary: 'decide', created_at: 2}) "
        "CREATE (d)-[:BASED_ON]->(f) CREATE (a)-[:DECIDED]->(d)",
        top=top,
    )
    return {"source": "src-d", "layers": layers, "top": top, "decision": "dec-d", "agent": "ag-d"}


def build_tasks(relay, *, levels: int = 8, width: int = 18, fan_in: int = 3) -> list[list[str]]:
    """Root + ``levels`` layers; returns the layers (root first). 1 + 8 * 18 = 145 tasks by default."""
    relay.create_tasks([{"id": "root", "title": "root"}])
    layers = [["root"]]
    for lv in range(1, levels + 1):
        prev = layers[-1]
        ids = [f"T{lv}-{j}" for j in range(width)]
        relay.create_tasks(
            [
                {
                    "id": t,
                    "title": t,
                    "depends_on": sorted({prev[(j + k) % len(prev)] for k in range(fan_in)}),
                }
                for j, t in enumerate(ids)
            ]
        )
        layers.append(ids)
    return layers
