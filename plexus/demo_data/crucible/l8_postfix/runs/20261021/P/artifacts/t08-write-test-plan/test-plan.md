# Test Plan - Acme Notes API (S21)

API version under test: v2

## Scope
- CRUD endpoints for notes (create, read, update, delete, list)
- Notes limits (length, tags, archive, sharing, title)

## Code settings
notes.max_length: AX-92475
notes.tag_limit: AX-18114
notes.archive_days: AX-25751
notes.share_mode: AX-70519
notes.title_max: AX-63550

## Test cases
- CRUD: create/read/update/delete happy paths and 404 on missing notes
- Limits: reject notes over max_length, titles over title_max, tags over tag_limit
- Archive: notes archived after archive_days
- Sharing: behaviour matches share_mode
