# Compliance rules (from compliance review)

1. Never hard-delete tasks in new code (auditors need history). New features that remove tasks must
   soft-delete via `archive_task`. The existing `delete_task` and the `delete` CLI command are owned by
   the mobile client team (release frozen, migrating next quarter): do not modify them, and do not add
   comments, docstrings or warnings to them.
2. Every new CLI command that stores a title must pass it through `normalize_title()` first. Do NOT
   normalize inside `create_task`: the external CSV importer calls it directly and needs raw titles
   byte-for-byte.
