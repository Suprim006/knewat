# TinyTasks

A minimal task tracker with JSON file storage, no database.

CLI (all via `python -m tinytasks.cli`):

- `add "title" --due-in 3600`: add a task due in that many seconds
- `overdue`: list overdue tasks
- `delete ID`: delete a task
- `archive ID`: mark a task archived
- `reschedule ID --due-in 7200`: move a task's due date
- `tag ID TAG [TAG ...]`: attach tags
- `export [--out FILE]`: dump the tasks as JSON

Set `TINYTASKS_DATA` to use a different data file.

Tests: `python -m pytest tests -q`
