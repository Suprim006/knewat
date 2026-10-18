# Acme Notes API S21 - Test Plan

API version: v2

## Scope
- CRUD endpoints for notes (create, read, update, delete, list)
- Notes limits (length, tags, title, archive, sharing)

## Code settings
notes.max_length: AX-24538
notes.tag_limit: AX-19959
notes.archive_days: AX-87154
notes.share_mode: AX-39123
notes.title_max: AX-89547

## Test cases
- Create/read/update/delete a note returns correct status codes and bodies.
- Notes exceeding notes.max_length or title longer than notes.title_max are rejected.
- Notes with more tags than notes.tag_limit are rejected.
- Notes are archived after notes.archive_days; sharing follows notes.share_mode.
