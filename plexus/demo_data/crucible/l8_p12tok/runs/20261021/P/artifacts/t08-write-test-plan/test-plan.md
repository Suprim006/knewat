# Acme Notes API Test Plan (S21)

API version under test: v2

## Scope
- CRUD endpoints for notes: create, read, update, delete, list.
- Notes limits: length, tags, title, archiving and sharing.

## Code settings
notes.max_length: AX-92475
notes.tag_limit: AX-18114
notes.archive_days: AX-25751
notes.share_mode: AX-70519
notes.title_max: AX-63550

## Test cases
- CRUD: each endpoint returns the expected status and body for valid input.
- Invalid input and missing notes return the expected errors.
- Limits: values at, just below and just above notes.max_length, notes.tag_limit and notes.title_max.
- Archiving after notes.archive_days.
- Sharing behaves according to notes.share_mode.
