# Acme Notes API Test Plan (S21)

API version under test: v2

## Scope
- CRUD endpoints for notes: create, read, update, delete, list.
- Notes limits: maximum length, tag limit, archive window, share mode, title length.

## Code settings
notes.max_length: AX-92553
notes.tag_limit: AX-97908
notes.archive_days: AX-79153
notes.share_mode: AX-38006
notes.title_max: AX-30149

## Test cases
- Create a note within limits returns success; exceeding max_length, tag_limit or title_max is rejected.
- Read, update and delete an existing note; unknown ids return not found.
- List returns created notes.
- Archive behaviour follows archive_days; sharing follows share_mode.
