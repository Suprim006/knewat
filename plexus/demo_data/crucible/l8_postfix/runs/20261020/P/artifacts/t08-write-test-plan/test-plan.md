# Acme Notes API - Test Plan (S21)

API version under test: v2

## Scope
- CRUD endpoints for notes (create, read, update, delete, list)
- Notes limits (length, tags, archiving, sharing, title)

## Code settings under test
notes.max_length: AX-92553
notes.tag_limit: AX-97908
notes.archive_days: AX-79153
notes.share_mode: AX-38006
notes.title_max: AX-30149

## Test cases
- Create/read/update/delete a note; verify status codes and payloads.
- Reject notes exceeding notes.max_length and titles exceeding notes.title_max.
- Reject tag counts above notes.tag_limit.
- Verify archiving after notes.archive_days.
- Verify sharing behaviour per notes.share_mode.
