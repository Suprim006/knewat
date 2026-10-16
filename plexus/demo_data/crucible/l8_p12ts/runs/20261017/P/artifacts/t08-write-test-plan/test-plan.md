# Test Plan: Acme Notes API (S21)

API version under test: v2

## Scope
- CRUD endpoints for notes (create, read, update, delete, list)
- Notes limits (length, tags, title, archive, sharing)

## Code settings
notes.max_length: AX-21323
notes.tag_limit: AX-33384
notes.archive_days: AX-34286
notes.share_mode: AX-31441
notes.title_max: AX-43136

## Test cases
- Create/read/update/delete a note: success and not-found paths.
- Boundary tests at and above notes.max_length and notes.title_max.
- Reject notes exceeding notes.tag_limit tags.
- Archive behaviour after notes.archive_days.
- Sharing behaviour per notes.share_mode.
