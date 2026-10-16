"""A stdio MCP server with ONE tool, ``query(sql)``: read-only SQL over an L6 SQLite store (arm B1a).

    python -m plexus.crucible.l6.sql_mcp --db <path to crucible.db>

Only ``SELECT`` / ``WITH`` / ``EXPLAIN`` statements are accepted, the database is opened ``mode=ro``, a statement is
interrupted after 20 s, and a result is cut at 200 rows / 12,000 characters (the cut is announced), so a runaway query
cannot flood the model's context. Nothing else is exposed.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
import time
from pathlib import Path
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

MAX_ROWS, MAX_CHARS, TIMEOUT_S = 200, 12_000, 20.0
ALLOWED = ("select", "with", "explain")


def run_query(conn: sqlite3.Connection, sql: str, deadline_box: list[float]) -> str:
    s = sql.strip().rstrip(";").strip()
    if not s.lower().startswith(ALLOWED):
        raise ToolError("only SELECT / WITH / EXPLAIN statements are allowed")
    if ";" in s:
        raise ToolError("one statement per call")
    deadline_box[0] = time.perf_counter() + TIMEOUT_S
    try:
        cur = conn.execute(s)
        rows = cur.fetchmany(MAX_ROWS + 1)
    except sqlite3.OperationalError as exc:
        if "interrupted" in str(exc):
            raise ToolError(f"statement interrupted after {TIMEOUT_S:.0f} s: make it cheaper") from None
        raise ToolError(f"SQL error: {exc}") from None
    except sqlite3.Error as exc:
        raise ToolError(f"SQL error: {exc}") from None
    cols = [c[0] for c in cur.description or []]
    more = len(rows) > MAX_ROWS
    lines = ["\t".join(cols)] + ["\t".join("" if v is None else str(v) for v in r) for r in rows[:MAX_ROWS]]
    text = "\n".join(lines)
    note = ""
    if more:
        note = f"\n[cut: more than {MAX_ROWS} rows; add LIMIT or aggregate]"
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
        note = f"\n[cut at {MAX_CHARS} characters]"
    return text + note


def build(db: str) -> MCPServer:
    conn = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True, check_same_thread=False)
    conn.execute("PRAGMA query_only=ON")
    box = [0.0]
    conn.set_progress_handler(lambda: 1 if time.perf_counter() > box[0] else 0, 20000)
    mcp = MCPServer(
        "sql", instructions="Read-only SQL over the team's recorded memory (SQLite).", log_level="WARNING"
    )

    @mcp.tool()
    def query(sql: Annotated[str, Field(description="One read-only SQLite SELECT / WITH statement.")]) -> str:
        """Run one read-only SQL statement on the memory database; returns tab-separated rows (at most 200)."""
        return run_query(conn, sql, box)

    return mcp


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="crucible-l6-sql-mcp")
    ap.add_argument("--db", required=True)
    a = ap.parse_args(argv)
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    build(a.db).run("stdio")


if __name__ == "__main__":
    main()
