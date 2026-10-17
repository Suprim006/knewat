# Acme Notes API S21 - Test Plan

API version: v2

## Scope
- CRUD endpoints for notes (create, read, update, delete, list)
- Notes limits (length, tags, archive, sharing, title)

## Code settings under test
notes.max_length: AX-21323
notes.tag_limit: AX-33384
notes.archive_days: AX-34286
notes.share_mode: AX-31441
notes.title_max: AX-43136

## Test cases
- CRUD: each endpoint returns the expected status and body for valid input; 404 for unknown ids.
- Limits: boundary tests at, below and above each setting above.
