# Acme Notes API S21 - Test Plan

API version under test: v2

## Scope
- CRUD endpoints for notes: create, read, update, delete, list.
- Notes limits: length, tag count, archive period, share mode, title length.

## Code settings
notes.max_length: AX-21323
notes.tag_limit: AX-33384
notes.archive_days: AX-34286
notes.share_mode: AX-31441
notes.title_max: AX-43136

## Test cases
1. Create: valid note succeeds; note over notes.max_length is rejected; title over notes.title_max is rejected.
2. Read: existing note returns 200; missing note returns 404.
3. Update: changes persist; limits re-validated.
4. Delete: note removed; repeated delete returns 404.
5. Tags: adding more than notes.tag_limit tags is rejected.
6. Archive: notes are archived after notes.archive_days.
7. Share: sharing behaves according to notes.share_mode.
