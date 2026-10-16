# Acme Notes API S21 - Test Plan

## Scope
CRUD endpoints for notes (create, read, update, delete, list) and the notes limits below.
API version: the recall for "API version" returned no S21 entry (only other sprints), so the S21 version is not confirmed here.

## Code settings (from repo/notes.py)
notes.max_length: AX-21323
notes.tag_limit: AX-33384
notes.archive_days: AX-34286
notes.share_mode: AX-31441
notes.title_max: AX-43136

## Test cases
- Create: valid note returns success; title longer than notes.title_max is rejected; body longer than notes.max_length is rejected.
- Read/List: created note is retrievable; list returns all notes.
- Update: edits persist; the same length limits apply.
- Delete: note is removed and later reads fail.
- Tags: adding tags beyond notes.tag_limit is rejected.
- Archive: notes are archived per notes.archive_days.
- Sharing: sharing behaves according to notes.share_mode.
