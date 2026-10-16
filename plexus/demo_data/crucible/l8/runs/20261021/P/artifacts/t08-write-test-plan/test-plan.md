# Acme Notes API Test Plan (S21)

API version under test: v2

## Scope
- CRUD endpoints for notes: create, read, update, delete, list
- Notes limits: length, tag count, archive period, sharing mode, title length

## Code settings
notes.max_length: AX-92475
notes.tag_limit: AX-18114
notes.archive_days: AX-25751
notes.share_mode: AX-70519
notes.title_max: AX-63550

## Test cases
- Create a note within limits returns success; exceeding notes.max_length or notes.title_max is rejected.
- Adding tags beyond notes.tag_limit is rejected.
- Read, update and delete an existing note; a missing note returns not found.
- Notes older than notes.archive_days are archived.
- Sharing behaves according to notes.share_mode.
