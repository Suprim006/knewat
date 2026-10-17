# Acme Notes API S21 - Test Plan

API version under test: v2

## Scope
- CRUD endpoints for notes (create, read, update, delete, list)
- Notes limits (length, tags, archiving, sharing, title size)

## Code settings
notes.max_length: AX-24538
notes.tag_limit: AX-19959
notes.archive_days: AX-87154
notes.share_mode: AX-39123
notes.title_max: AX-89547

## Test cases
- CRUD: create/read/update/delete a note; list notes; 404 on missing note.
- Limits: reject content over max_length, titles over title_max, tags over tag_limit.
- Archive: notes archive after archive_days.
- Share: sharing behaves per share_mode.
