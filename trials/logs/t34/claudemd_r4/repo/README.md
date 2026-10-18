# TinyTasks

A minimal task tracker: add tasks with a due time, list overdue ones, delete them. JSON file
storage, no database.

CLI: `python -m tinytasks.cli add "title" --due-in 3600`, `python -m tinytasks.cli overdue`,
`python -m tinytasks.cli delete 3`. Set `TINYTASKS_DATA` to use a different data file.

Tests: `python -m pytest tests -q`
