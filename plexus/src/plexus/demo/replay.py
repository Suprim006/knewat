"""Replay a recording: restore ``graph.dump`` into a tenant graph and verify the inventory against ``meta.json``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from plexus.demo.inventory import inventory
from plexus.demo.recorder import DUMP_NAME, load_meta, raw_connection, run_dir
from plexus.graph.client import GraphClient
from plexus.graph.tenancy import graph_name


class ReplayError(RuntimeError):
    pass


def replay(
    client: GraphClient, run: str, tenant: str, *, reset: bool = False, root: Path | None = None
) -> dict[str, Any]:
    """Restore recording ``run`` as tenant ``tenant``.

    Refuses to overwrite a tenant that already has a graph unless ``reset``. Returns ``{'meta', 'inventory',
    'matches'}``; ``matches`` is true when the restored node and edge counts per label / type equal ``meta.json``.
    """
    meta = load_meta(run, root)
    blob = (run_dir(run, root) / DUMP_NAME).read_bytes()
    key = graph_name(tenant)
    raw = raw_connection(client)
    if raw.exists(key) and not reset:
        raise ReplayError(f"tenant '{tenant}' already has a graph; pass reset=True (--reset) to overwrite it")
    raw.restore(key, 0, blob, replace=True)
    inv = inventory(client, tenant)
    want = meta["inventory"]
    matches = inv["nodes"] == want["nodes"] and inv["edges"] == want["edges"]
    return {"meta": meta, "inventory": inv, "matches": matches}
