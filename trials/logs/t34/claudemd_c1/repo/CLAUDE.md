# tinytasks conventions (from compliance review)

- Never hard-delete tasks in new code (auditors need history). Any new feature that removes tasks must soft-delete via `archive_task`.
- `delete_task` and the `delete` CLI command are legacy, owned by the mobile client team (release frozen, migrating next quarter). Do not modify them or add comments/docstrings/warnings to them.
- Every new CLI command that stores a title must pass it through `normalize_title()` (tinytasks/text.py) first.
- Do NOT normalize inside `create_task`: the external CSV importer calls it directly and must keep raw titles byte-for-byte.
