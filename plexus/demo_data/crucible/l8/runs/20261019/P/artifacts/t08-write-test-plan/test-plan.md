# Acme Notes API Test Plan (S21)

API version under test: v2

## Scope
- CRUD endpoints for notes (create, read, update, delete, list)
- Notes limits (length, tags, archiving, sharing, title)

## Code settings
notes.max_length: AX-16383
notes.tag_limit: AX-60457
notes.archive_days: AX-94273
notes.share_mode: AX-43223
notes.title_max: AX-40109

## Test cases
- CRUD happy path for each endpoint
- Reject notes exceeding notes.max_length
- Reject notes exceeding notes.tag_limit tags
- Reject titles longer than notes.title_max
- Archive behaviour after notes.archive_days
- Sharing behaviour per notes.share_mode
