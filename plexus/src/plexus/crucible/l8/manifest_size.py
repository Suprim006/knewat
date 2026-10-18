"""$0 size of the published Plexus tool list: what the MCP manifest costs on EVERY model call, without a model call.

    python -m plexus.crucible.l8.manifest_size [--toolset core --toolset full] [--out FILE]

``manifest_probe`` measures the same thing in API prompt tokens with one paid ``claude -p`` call per variant. This
script builds the server in memory (no database call is made: listing tools touches no graph), lists the tools a
session of each toolset would see, and counts the characters of each tool's ``{name, description, inputSchema}`` as
compact JSON, which is what the client puts in the prompt. Characters are a stable proxy (about 3.5 characters per
token on this JSON); compare two runs of this script, not a run of this script with a probe number.
Output: one JSON object ``{toolset: {tools, description_chars, schema_chars, total_chars}}`` on stdout.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from mcp import Client
from plexus.embed import HashEmbedder
from plexus.graph.client import GraphClient
from plexus.graph.queries import QueryLibrary
from plexus.mcp.runtime import Runtime
from plexus.mcp.server import build_server


async def measure(toolset: str) -> dict[str, int]:
    client = GraphClient(host="127.0.0.1", port=6379, password="", library=QueryLibrary())  # never connected
    rt = Runtime(client=client, embedder=HashEmbedder(), stdio_tenant="manifest_size")
    async with Client(build_server(rt, toolset)) as c:
        tools = (await c.list_tools()).tools
    desc = schema = 0
    for t in tools:
        desc += len(t.description or "")
        schema += len(json.dumps(t.input_schema, separators=(",", ":"), sort_keys=True))
        schema += len(t.name)
    return {
        "tools": len(tools),
        "description_chars": desc,
        "schema_chars": schema,
        "total_chars": desc + schema,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--toolset", action="append", default=[])
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    out = {ts: asyncio.run(measure(ts)) for ts in (a.toolset or ["core", "full"])}
    text = json.dumps(out, indent=2) + "\n"
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
