# tasksync

Small exporter CLI. It reads the JSON data file that the sibling `tinytasks` project keeps and
writes exports of it for other tools.

Data file: `--data PATH`, else the `TINYTASKS_DATA` environment variable, else
`../tinytasks/tinytasks/data.json`. It is a JSON list of task objects:
`{"id": 3, "title": "write report", "due_at": 1791000000.0, "archived": false}`
(`due_at` is a Unix timestamp in seconds; `archived` is set by tinytasks' `archive_task`).

Commands: `python -m tasksync.cli export-json OUT` writes every task to OUT as JSON.
`python -m tasksync.cli --data tasks.json export-json out.json` uses a specific data file.

Tests: `python -m pytest tests -q`
