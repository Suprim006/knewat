# Test Plan - Acme Notes API (S21)

API version: v2

## Scope
- CRUD endpoints for notes (create, read, update, delete, list)
- Notes limits (length, tags, archive, sharing, title)

## Code settings under test
notes.max_length: AX-16383
notes.tag_limit: AX-60457
notes.archive_days: AX-94273
notes.share_mode: AX-43223
notes.title_max: AX-40109

## Cases
- CRUD: each endpoint returns the expected status and body for valid input and rejects invalid input.
- Limits: boundary tests at, below and above each setting above.
