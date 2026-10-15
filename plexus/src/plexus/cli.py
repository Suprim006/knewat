"""``plexus`` command line: ``plexus demo seed | live | record | replay | inventory | list | ablation`` and
``plexus mcp-config``.

Connection settings come from the usual env vars (``FALKORDB_HOST``, ``FALKORDB_PORT``, ``FALKORDB_PASSWORD``).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from plexus.codescan.cli import add_code_commands
from plexus.demo.scenario import FaultScript, load_scenario
from plexus.graph.client import GraphClient
from plexus.graph.tenancy import graph_name

DEFAULT_TENANT = "demo"
STEP_SECONDS = 0.5  # pause per tool call at --speed 1


def _client() -> GraphClient:
    return GraphClient()


def _embedder(kind: str | None):
    if not kind:
        return None  # the Runtime picks PLEXUS_EMBEDDER / fastembed lazily
    from plexus.embed import HashEmbedder

    if kind == "hash":
        return HashEmbedder()
    from plexus.mcp.embedding import make_embedder

    return make_embedder()


def _tenant_has_data(client: GraphClient, tenant: str) -> bool:
    try:
        rows = client.ro(graph_name(tenant), "view/inventory_nodes")
    except Exception:  # graph does not exist yet
        return False
    return any(r["n"] for r in rows)


def _prepare_tenant(client: GraphClient, tenant: str, reset: bool) -> None:
    graph_name(tenant)  # validates the name
    if reset:
        client.delete_graph(graph_name(tenant))
    elif _tenant_has_data(client, tenant):
        raise SystemExit(
            f"tenant '{tenant}' already has data. Pick another --tenant or pass --reset to wipe it first."
        )


# ------------------------------------------------------------------------------------------------ commands
def cmd_seed(a: argparse.Namespace) -> int:
    """Apply the schema to the tenant and register the documents that exist before the run starts as Sources."""
    from plexus.graph.schema import apply_schema
    from plexus.lineage import Lineage

    client = _client()
    _prepare_tenant(client, a.tenant, a.reset)
    graph = graph_name(a.tenant)
    apply_schema(client, graph)
    lin = Lineage(client, graph)
    sc = load_scenario()
    late = {"06_api_style_guide_v2", "07_forum_post_unverified"}  # published mid-run
    n = 0
    for stem, doc in sc.sources.items():
        if stem in late:
            continue
        lin.create_source(doc.uri, doc.kind, doc.trust, title=doc.title, text=doc.text)
        n += 1
    print(
        f"tenant '{a.tenant}': schema applied, {n} Source nodes seeded (v2 guide and forum post arrive mid-run)"
    )
    return 0


def cmd_live(a: argparse.Namespace) -> int:
    if a.claude:
        from plexus.demo.orchestrator import cli_run_claude

        return cli_run_claude(a)
    if not a.scripted:
        raise SystemExit(
            "choose a mode: --scripted (deterministic agents) or --claude (real claude -p agents)"
        )
    from plexus.demo.scripted import run_scripted

    a.tenant = a.tenant or DEFAULT_TENANT
    client = _client()
    _prepare_tenant(client, a.tenant, a.reset)
    faults = FaultScript(
        kill_builder_at=None if a.no_faults else a.kill_at,
        publish_v2_at=None if a.no_faults else a.v2_at,
        poison_at=a.poison_at,
        builder_lease_ms=a.lease_ms or 3000,
    )
    pace = STEP_SECONDS / a.speed if a.speed > 0 else 0.0

    def show(rec: dict) -> None:
        print(f"step {rec['step']:>3}  {rec['agent']:<10} {rec['tool']}", flush=True)

    w = asyncio.run(
        run_scripted(
            a.tenant, client, embedder=_embedder(a.embedder), faults=faults, pace_s=pace, on_call=show
        )
    )
    print()
    for ev in w.events:
        info = {k: v for k, v in ev.items() if k not in ("event", "step", "t", "blast_radius")}
        print(f"fault/event @step {ev['step']:>3}: {ev['event']}  {info}")
    print(f"\nscripted run finished: {w.step} tool calls, tenant '{a.tenant}'")
    if a.record:
        from plexus.demo.recorder import record_run

        meta = record_run(client, a.tenant, a.record, mode="scripted", world=w)
        print(
            f"recorded as '{a.record}': {meta['inventory']['total_nodes']} nodes, {meta['inventory']['total_edges']} edges"
        )
    return 0


def cmd_inventory(a: argparse.Namespace) -> int:
    from plexus.demo.inventory import format_inventory, inventory

    print(format_inventory(inventory(_client(), a.tenant)))
    return 0


def cmd_record(a: argparse.Namespace) -> int:
    from plexus.demo.recorder import record_run

    meta = record_run(_client(), a.tenant, a.run, mode=a.mode)
    print(
        f"recorded '{a.run}': {meta['inventory']['total_nodes']} nodes, {meta['inventory']['total_edges']} edges"
    )
    return 0


def cmd_replay(a: argparse.Namespace) -> int:
    from plexus.demo.replay import replay

    client = _client()
    graph_name(a.tenant)
    res = replay(client, a.run, a.tenant, reset=a.reset)
    print(
        f"replayed '{a.run}' into tenant '{a.tenant}': {res['inventory']['total_nodes']} nodes, "
        f"{res['inventory']['total_edges']} edges (matches meta.json: {res['matches']})"
    )
    return 0 if res["matches"] else 1


def cmd_list(a: argparse.Namespace) -> int:
    from plexus.demo.recorder import list_recordings

    for m in list_recordings():
        print(
            f"{m['run']:<28} {m['mode']:<9} {m['inventory']['total_nodes']:>5} nodes  {m['inventory']['total_edges']:>5} edges  {m.get('model', '')}"
        )
    return 0


def cmd_ablation(a: argparse.Namespace) -> int:
    """Copy the tenant, cut DEPENDS_ON / BASED_ON / DERIVED_FROM / READ in the copy, probe both side by side."""
    import json

    from plexus.demo.ablation import format_report, run_ablation, to_dict

    graph_name(a.tenant)
    client = _client()
    report = run_ablation(client, a.tenant, drop=a.drop, log=(lambda _m: None) if a.json else print)
    print(json.dumps(to_dict(report), indent=2) if a.json else "\n" + format_report(report))
    return 0 if report.as_expected else 1


def cmd_mcp_config(a: argparse.Namespace) -> int:
    """Print (or write) an MCP config for this checkout: stdio via the venv's plexus-mcp, or streamable HTTP."""
    import json
    from pathlib import Path

    from plexus.demo.orchestrator import build_http_mcp_config, build_mcp_config

    graph_name(a.tenant)  # validates the tenant name
    try:
        cfg = build_http_mcp_config(a.http, a.tenant) if a.http else build_mcp_config(a.tenant, a.mcp_command)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    text = json.dumps(cfg, indent=2)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {a.out}", file=sys.stderr)
    else:
        print(text)
    return 0


# ------------------------------------------------------------------------------------------------ parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="plexus", description="Plexus command line")
    sub = p.add_subparsers(dest="group", required=True)
    demo = sub.add_parser("demo", help="the Acme Notes API demo scenario")
    ds = demo.add_subparsers(dest="cmd", required=True)

    def tenant_arg(sp: argparse.ArgumentParser, default: str = DEFAULT_TENANT) -> None:
        sp.add_argument(
            "--tenant", default=default, help=f"tenant (graph plexus_t_<tenant>), default '{default}'"
        )

    s = ds.add_parser("seed", help="apply the schema and register the starting documents as Sources")
    tenant_arg(s)
    s.add_argument("--reset", action="store_true", help="drop the tenant's graph first")
    s.set_defaults(fn=cmd_seed)

    s = ds.add_parser("live", help="run the scenario live: scripted agents or real claude -p agents")
    tenant_arg(s, None)
    mode = s.add_mutually_exclusive_group()
    mode.add_argument(
        "--scripted", action="store_true", help="deterministic non-LLM agents through the MCP tools"
    )
    mode.add_argument(
        "--claude", action="store_true", help="3 real claude -p agents (spends the owner's subscription)"
    )
    s.add_argument(
        "--speed", type=float, default=1.0, help="scripted: steps per half second; 0 = no pause (default 1)"
    )
    s.add_argument("--reset", action="store_true", help="drop the tenant's graph first")
    s.add_argument("--embedder", choices=["hash", "fastembed"], help="scripted: override PLEXUS_EMBEDDER")
    s.add_argument("--kill-at", type=int, default=15, help="kill the builder from this step (default 15)")
    s.add_argument("--v2-at", type=int, default=20, help="publish style guide v2 from this step (default 20)")
    s.add_argument(
        "--poison-at", type=int, default=None, help="(stretch) inject the poisoned forum post from this step"
    )
    s.add_argument("--no-faults", action="store_true", help="scripted: run without the kill and v2 faults")
    s.add_argument(
        "--lease-ms",
        type=int,
        default=None,
        help="the builder's lease (default 3000 ms scripted, 45000 claude)",
    )
    s.add_argument(
        "--stop-after-turns", type=int, default=None, help="claude: stop after N agent turns (a cheap pilot)"
    )
    s.add_argument("--record", metavar="RUN", help="after the run, record it as demo_data/recordings/RUN")
    s.add_argument("--model", default="sonnet", help="claude: model alias (default sonnet)")
    s.add_argument("--max-turns", type=int, default=25, help="claude: max turns per agent turn (default 25)")
    s.add_argument("--run-name", help="claude: run name / recording directory (default claude-<timestamp>)")
    s.add_argument(
        "--mcp-command", help="claude: path of plexus-mcp (default: the venv script next to python)"
    )
    s.set_defaults(fn=cmd_live)

    s = ds.add_parser("record", help="record a tenant's graph as demo_data/recordings/<run>")
    s.add_argument("run")
    tenant_arg(s)
    s.add_argument("--mode", default="scripted", choices=["scripted", "claude"])
    s.set_defaults(fn=cmd_record)

    s = ds.add_parser("replay", help="restore a recording into a tenant and verify its inventory")
    s.add_argument("run", help="recording name (see 'plexus demo list')")
    tenant_arg(s)
    s.add_argument("--reset", action="store_true", help="overwrite the tenant if it has data")
    s.set_defaults(fn=cmd_replay)

    s = ds.add_parser("inventory", help="node and edge counts of a tenant")
    tenant_arg(s)
    s.set_defaults(fn=cmd_inventory)

    s = ds.add_parser("list", help="list the recordings")
    s.set_defaults(fn=cmd_list)

    s = ds.add_parser(
        "ablation",
        help="copy a tenant, cut DEPENDS_ON/BASED_ON/DERIVED_FROM/READ in the copy and show what breaks",
    )
    tenant_arg(s)
    s.add_argument("--drop", action="store_true", help="drop the <tenant>_ablated copy afterwards")
    s.add_argument("--json", action="store_true", help="print the result as JSON")
    s.set_defaults(fn=cmd_ablation)

    m = sub.add_parser(
        "mcp-config",
        help="print an MCP config for Claude Code (stdio via this checkout's venv, or --http URL)",
    )
    tenant_arg(m)
    m.add_argument(
        "--http", metavar="URL", help="streamable-HTTP endpoint (e.g. http://127.0.0.1:8765) instead of stdio"
    )
    m.add_argument(
        "--mcp-command", help="stdio: path of plexus-mcp (default: the venv script next to python)"
    )
    m.add_argument("--out", metavar="FILE", help="write the config to FILE instead of printing it")
    m.set_defaults(fn=cmd_mcp_config)
    add_code_commands(sub)  # P7-J: plexus code scan | baseline | hook-claude | hook-git | hook-run
    return p


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        code = args.fn(args)
    except KeyboardInterrupt:
        code = 130
    sys.exit(code)


if __name__ == "__main__":
    main()
