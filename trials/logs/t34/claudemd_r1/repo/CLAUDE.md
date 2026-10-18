# TinyTasks conventions

Compliance rules (from compliance review):

1. No new code may hard-delete tasks (auditors need history). Features that remove tasks must
   soft-delete via `archive_task`. The existing `delete_task` and the `delete` CLI command are
   owned by the mobile client team (release frozen, migrating next quarter): do NOT modify
   them, and do not add comments, docstrings or warnings to them.
2. Every new CLI command that stores a title must pass it through `normalize_title()`
   (tinytasks/text.py) first. Do NOT normalize inside `create_task`: an external CSV importer
   calls it directly and must keep raw titles byte-for-byte.
