# TinyTasks conventions

Compliance rules (decided in compliance review; apply to all future work):

1. Never hard-delete tasks in new code (auditors need history). Features that remove tasks must soft-delete via `archive_task`.
   - Exception: the existing `delete_task` and the `delete` CLI command are owned by the mobile client team (release frozen, migrating next quarter). Do not modify them, and do not add comments/docstrings/warnings to them.
2. Every new CLI command that stores a title must pass it through `normalize_title()` (tinytasks/text.py) first.
   - Do NOT normalize inside `create_task`: the external CSV importer calls it directly and must keep raw titles byte-for-byte.
