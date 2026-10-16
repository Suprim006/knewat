# Acme Notes API Test Plan (S21)

API version under test: v2

## Scope
- CRUD endpoints for notes: create, read, update, delete, list
- Notes limits (see settings below)

## Code settings
notes.max_length: AX-92553
notes.tag_limit: AX-97908
notes.archive_days: AX-79153
notes.share_mode: AX-38006
notes.title_max: AX-30149

## Test cases
1. Create: valid note returns success; title at and above title_max; body at and above max_length is handled per limit.
2. Read: existing note returns data; missing note returns not found.
3. Update: valid update persists; over-limit values rejected.
4. Delete: existing note removed; repeat delete returns not found.
5. List: returns created notes.
6. Tags: count at and above tag_limit.
7. Archive: notes older than archive_days are archived.
8. Sharing: behaviour matches share_mode.
