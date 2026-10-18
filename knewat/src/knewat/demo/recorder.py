"""Record a finished run: snapshot the tenant graph to ``demo_data/recordings/<run>/graph.dump`` + ``meta.json``.

The snapshot is ``GRAPH.COPY`` of the tenant graph to ``rec_<run>``, then Redis ``DUMP`` of that copy (the copy is
dropped again). ``DUMP``/``RESTORE`` round-trips nodes, edges, properties, vectors and indexes on FalkorDB 6.0.2
(verified in ``tests/demo/test_recorder.py``); a dump is only valid for the FalkorDB version that wrote it, which
``meta.json`` records.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import redis

from knewat.demo.engine import World
from knewat.demo.inventory import inventory
from knewat.demo.scenario import recordings_dir
from knewat.graph.client import GraphClient
from knewat.graph.tenancy import graph_name

_RUN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,60}")
DUMP_NAME = "graph.dump"
META_NAME = "meta.json"


def check_run_name(run: str) -> str:
    if not _RUN_RE.fullmatch(run):
        raise ValueError(f"invalid run name {run!r}: use letters, digits, '_', '-' or '.'")
    return run


def raw_connection(client: GraphClient) -> redis.Redis:
    """A Redis connection that returns bytes (DUMP/RESTORE payloads are binary)."""
    kw = client.db.connection.connection_pool.connection_kwargs
    keep = {k: kw[k] for k in ("host", "port", "username", "password", "db") if kw.get(k) is not None}
    return redis.Redis(decode_responses=False, **keep)


def falkordb_version(client: GraphClient) -> str:
    try:
        mods = client.db.connection.execute_command("MODULE", "LIST")
    except redis.RedisError:
        return ""
    for m in mods:
        d = {(k.decode() if isinstance(k, bytes) else k): v for k, v in zip(m[::2], m[1::2], strict=False)}
        if str(d.get("name", "")).lower() in ("graph", "falkordb"):
            return str(d.get("ver", ""))
    return ""


def run_dir(run: str, root: Path | None = None) -> Path:
    return (root or recordings_dir()) / check_run_name(run)


def snapshot(client: GraphClient, tenant: str, run: str) -> bytes:
    """``GRAPH.COPY`` the tenant graph to ``rec_<run>``, ``DUMP`` the copy, drop the copy."""
    src, copy = graph_name(tenant), f"rec_{re.sub(r'[^A-Za-z0-9_]', '_', run)}"
    client.delete_graph(copy)
    client.db.connection.execute_command("GRAPH.COPY", src, copy)
    try:
        blob = raw_connection(client).dump(copy)
    finally:
        client.delete_graph(copy)
    if not blob:
        raise RuntimeError(f"DUMP of {copy} returned nothing (does tenant '{tenant}' have a graph?)")
    return blob


def record_run(
    client: GraphClient,
    tenant: str,
    run: str,
    *,
    mode: str = "scripted",
    world: World | None = None,
    claude: dict[str, Any] | None = None,
    transcripts: dict[str, str] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Write the recording for ``run`` (graph dump, meta.json, transcripts); returns the meta dict."""
    out = run_dir(run, root)
    out.mkdir(parents=True, exist_ok=True)
    blob = snapshot(client, tenant, run)
    (out / DUMP_NAME).write_bytes(blob)
    meta: dict[str, Any] = {
        "run": run,
        "mode": mode,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source_tenant": tenant,
        "falkordb_version": falkordb_version(client),
        "dump_bytes": len(blob),
        "inventory": inventory(client, tenant),
    }
    if world is not None:
        tools: dict[str, int] = {}
        for c in world.calls:
            tools[c["tool"]] = tools.get(c["tool"], 0) + 1
        meta.update(
            steps=world.step,
            faults=world.faults.fired,
            events=world.events,
            tool_calls_by_tool=tools,
            turns=[
                {"kind": t.kind, "agent": t.agent, "name": t.name, "reclaim_from": t.reclaim_from}
                for t in world.turns
            ],
        )
        (out / "calls.json").write_text(json.dumps(world.calls, indent=1), encoding="utf-8")
    if claude:
        meta.update(claude)
    if transcripts:
        tdir = out / "transcripts"
        tdir.mkdir(exist_ok=True)
        for name, text in transcripts.items():
            (tdir / name).write_text(text, encoding="utf-8")
    (out / META_NAME).write_text(json.dumps(meta, indent=2, default=str) + "\n", encoding="utf-8")
    return meta


def load_meta(run: str, root: Path | None = None) -> dict[str, Any]:
    p = run_dir(run, root) / META_NAME
    if not p.exists():
        raise FileNotFoundError(f"no recording '{run}' (expected {p})")
    return json.loads(p.read_text(encoding="utf-8"))


def list_recordings(root: Path | None = None) -> list[dict[str, Any]]:
    base = root or recordings_dir()
    if not base.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(base.glob(f"*/{META_NAME}"))]
