# Test Plan: Acme Notes API S21 (API version v2)

## Scope
- CRUD endpoints: create, read, update, delete notes
- Notes limits: length, tags, title, archive, sharing

## Code settings
notes.max_length: AX-24538
notes.tag_limit: AX-19959
notes.archive_days: AX-87154
notes.share_mode: AX-39123
notes.title_max: AX-89547

## Cases
- Create/read/update/delete happy paths under /v2
- Reject notes exceeding notes.max_length; titles exceeding notes.title_max
- Reject tag counts above notes.tag_limit
- Archive behaviour after notes.archive_days
- Sharing behaviour according to notes.share_mode
