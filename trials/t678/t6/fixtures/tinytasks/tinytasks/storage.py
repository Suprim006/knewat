"""Plain-JSON storage for tasks.

The data file defaults to tinytasks/data.json; set TINYTASKS_DATA to point elsewhere.
"""
import json
import os
from pathlib import Path

from tinytasks.models import Task

DEFAULT_PATH = Path(__file__).parent / "data.json"


def _resolve(path: Path | None) -> Path:
    if path is not None:
        return path
    env = os.environ.get("TINYTASKS_DATA")
    return Path(env) if env else DEFAULT_PATH


def load_all(path: Path | None = None) -> list[Task]:
    path = _resolve(path)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Task(**r) for r in raw]


def save_all(tasks: list[Task], path: Path | None = None) -> None:
    path = _resolve(path)
    path.write_text(json.dumps([t.__dict__ for t in tasks], indent=2), encoding="utf-8")


def next_id(tasks: list[Task]) -> int:
    return (max((t.id for t in tasks), default=0)) + 1
