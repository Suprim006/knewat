"""How many prompt tokens does the Plexus MCP tool list cost per API call? One ``claude -p`` call per variant.

    python -m plexus.crucible.l8.manifest_probe --workdir DIR --port 6366 [--head-src PATH]
        [--toolset core --toolset core,staleness ...] [--no-verbose]

Variants: ``none`` (no MCP server: Claude Code's own prompt + the five file tools), ``full``
(``PLEXUS_MCP_SCHEMA=full``: pydantic's verbose schemas), ``compact`` (the default) and, with ``--head-src``, the
server of another source tree (e.g. ``git archive HEAD plexus/src plexus/queries`` unpacked somewhere) run as
``python -m plexus.mcp.server`` with that ``PYTHONPATH``. The prompt is one short line and ``--max-turns 1``, so a
variant's prompt tokens minus ``none``'s are the tool list's tokens, exactly as the API counts them (~$0.14 a variant).
Each ``--toolset NAME`` adds a variant ``toolset:NAME`` (the compact list scoped with ``plexus-mcp --toolset NAME``,
see :mod:`plexus.mcp.toolsets`); ``--no-verbose`` skips the ``full`` (verbose-schema) variant.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

FILE_TOOLS = "Read,Write,Edit,Glob,Grep"


def probe(workdir: Path, name: str, server: dict | None) -> dict:
    cfg = {"mcpServers": {} if server is None else {"plexus": server}}
    path = workdir / f"mcp-{name}.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    allowed = f"mcp__plexus__*,{FILE_TOOLS}" if server else FILE_TOOLS
    cmd = ["claude", "-p", "Reply with the single word OK. Do not call any tool.", "--model", "sonnet",
           "--max-turns", "1", "--mcp-config", str(path), "--strict-mcp-config", "--allowedTools", allowed,
           "--tools", FILE_TOOLS, "--output-format", "json", "--no-session-persistence"]  # fmt: skip
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=workdir, timeout=300)
    j = json.loads(r.stdout)
    u = j["usage"]
    tokens = u["input_tokens"] + u["cache_creation_input_tokens"] + u["cache_read_input_tokens"]
    return {"prompt_tokens": tokens, "cost_usd": j["total_cost_usd"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workdir", type=Path, required=True)
    ap.add_argument("--port", default="6366")
    ap.add_argument("--head-src", default=None, help="PYTHONPATH of another plexus source tree to probe")
    ap.add_argument("--toolset", action="append", default=[], help="add a scoped variant (repeatable)")
    ap.add_argument("--no-verbose", action="store_true", help="skip the PLEXUS_MCP_SCHEMA=full variant")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    a.workdir.mkdir(parents=True, exist_ok=True)
    py = str(Path(sys.executable)).replace("\\", "/")
    env = {"FALKORDB_HOST": "127.0.0.1", "FALKORDB_PORT": str(a.port)}
    args = ["-m", "plexus.mcp.server", "--transport", "stdio", "--tenant", "manifestprobe"]
    variants: dict[str, dict | None] = {
        "none": None,
        "full": {"command": py, "args": args, "env": {**env, "PLEXUS_MCP_SCHEMA": "full"}},
        "compact": {"command": py, "args": args, "env": env},
    }
    if a.no_verbose:
        del variants["full"]
    for ts in a.toolset:
        variants[f"toolset:{ts}"] = {"command": py, "args": [*args, "--toolset", ts], "env": env}
    if a.head_src:
        variants["head"] = {"command": py, "args": args, "env": {**env, "PYTHONPATH": a.head_src}}
    out = {k: probe(a.workdir, k, v) for k, v in variants.items()}
    base = out["none"]["prompt_tokens"]
    for k, v in out.items():
        v["tool_list_tokens"] = v["prompt_tokens"] - base
        print(
            f"{k:<24} prompt {v['prompt_tokens']:>7,}  tool list {v['tool_list_tokens']:>7,}  ${v['cost_usd']:.4f}"
        )
    if a.out:
        a.out.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
