"""Exporters: each takes the loaded task dicts and writes a file."""
import json
import time
from pathlib import Path

from tasksync.timefmt import to_iso


def export_json(tasks: list[dict], out_path) -> int:
    """Write every task to out_path as JSON. Returns the number of tasks written."""
    rows = [{"id": t["id"], "title": t["title"], "due": to_iso(t["due_at"])} for t in tasks]
    payload = {"exported_at": to_iso(time.time()), "count": len(rows), "tasks": rows}
    Path(out_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return len(rows)
