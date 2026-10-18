# tinytasks conventions (from compliance review)

- Never hard-delete tasks in new code (auditors need history). Features that remove tasks must soft-delete via `archive_task`.
- Do not modify the existing `delete_task` function or the `delete` CLI command (no edits, comments, docstrings or warnings): the mobile client team owns them, their release is frozen, and they migrate next quarter.
- Every new CLI command that stores a title must pass it through `normalize_title()` (tinytasks/text.py) first.
- Do NOT put normalization inside `create_task`: the external CSV importer calls it directly and must keep raw titles byte-for-byte.
