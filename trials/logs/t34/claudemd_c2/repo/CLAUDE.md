# tinytasks conventions (from compliance review)

- Never hard-delete tasks in new code (auditors need history). New features that remove tasks must soft-delete via `archive_task`.
- The existing `delete_task` and the `delete` CLI command are owned by the mobile client team (release frozen, migrating next quarter). Do not modify them, including comments/docstrings.
- Every new CLI command that stores a title must pass it through `normalize_title()` (tinytasks/text.py) first.
- Do NOT normalize inside `create_task`: the external CSV importer calls it directly and needs raw titles byte-for-byte.
