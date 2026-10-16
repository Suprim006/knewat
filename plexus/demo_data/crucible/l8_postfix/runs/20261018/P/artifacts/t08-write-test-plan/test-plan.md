# Acme Notes API Test Plan (S21)

API version under test: v2

## Scope
- CRUD endpoints for notes (create, read, update, delete, list)
- Notes limits (length, tags, archive, sharing, title)

## Code settings
notes.max_length: AX-24538
notes.tag_limit: AX-19959
notes.archive_days: AX-87154
notes.share_mode: AX-39123
notes.title_max: AX-89547

## Test cases
- CRUD: each endpoint returns the expected status and body for valid input.
- Limits: reject notes over max_length, titles over title_max, and tag lists over tag_limit.
- Archive: notes older than archive_days are archived.
- Sharing: behaviour matches share_mode.
