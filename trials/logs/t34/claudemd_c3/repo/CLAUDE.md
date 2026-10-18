# tinytasks conventions

- Never hard-delete tasks in new code (audit history required). Features that remove tasks must soft-delete via `archive_task`.
- Do not modify the existing `delete_task` or the `delete` CLI command: owned by the mobile client team, release frozen, migrating next quarter.
- Every new CLI command that stores a title must pass it through `normalize_title()` (tinytasks/text.py) first.
- Do NOT normalize inside `create_task`: the external CSV importer calls it directly and must keep raw titles byte-for-byte.
