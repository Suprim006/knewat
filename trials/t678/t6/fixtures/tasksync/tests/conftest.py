import json

import pytest

# 1791000000 = 2026-10-03T04:00:00Z
TASKS = [
    {"id": 1, "title": "write report", "due_at": 1791000000.0, "archived": False},
    {"id": 2, "title": "renew licence", "due_at": 1791090000.0, "archived": True},
    {"id": 3, "title": "book venue", "due_at": 1791200000.0, "archived": False},
]


@pytest.fixture
def data_file(tmp_path):
    p = tmp_path / "tasks.json"
    p.write_text(json.dumps(TASKS), encoding="utf-8")
    return p
