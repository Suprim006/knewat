"""Reads the task list that tinytasks keeps in its JSON data file.

Each entry looks like {"id": 3, "title": "write report", "due_at": 1791000000.0, "archived": false};
due_at is a Unix timestamp in SECONDS.
"""
import json
import os
from pathlib import Path

DEFAULT_DATA = Path(__file__).resolve().parent.parent.parent / "tinytasks" / "tinytasks" / "data.json"


def data_path(path=None) -> Path:
    if path:
        return Path(path)
    env = os.environ.get("TINYTASKS_DATA")
    return Path(env) if env else DEFAULT_DATA


def load_tasks(path=None) -> list[dict]:
    p = data_path(path)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))
