# Acme Notes API S21 - Test Plan

API version under test: v2

## Scope
- CRUD endpoints for notes: create, read, update, delete, list.
- Notes limits: maximum length, tag limit, archive period, share mode, title length.

## Code settings
notes.max_length: AX-21323
notes.tag_limit: AX-33384
notes.archive_days: AX-34286
notes.share_mode: AX-31441
notes.title_max: AX-43136

## Test cases
- CRUD: each endpoint returns the expected status and body for valid input; 404 for missing notes.
- Limits: content at and above notes.max_length; tags at and above notes.tag_limit; title at and above notes.title_max.
- Archive: notes older than notes.archive_days are archived.
- Sharing: behaviour matches notes.share_mode.
