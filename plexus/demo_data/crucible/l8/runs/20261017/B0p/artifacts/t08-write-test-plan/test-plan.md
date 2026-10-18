# Test plan (Acme Notes API S21, API v2)

API version: v2 (acme-docs/06_api_style_guide_v2.md; v1 is withdrawn).

## Scope
- CRUD endpoints for notes: create, read, update, delete, list.
- Notes limits, as set in the code (repo/notes.py).

## Code settings under test
notes.max_length: AX-21323
notes.tag_limit: AX-33384
notes.archive_days: AX-34286
notes.share_mode: AX-31441
notes.title_max: AX-43136

## Test cases
1. Create a note with a valid title and body: expect success.
2. Create a note whose body is at notes.max_length and one over it: expect accept, then reject.
3. Create a note whose title is at notes.title_max and one over it: expect accept, then reject.
4. Attach tags up to notes.tag_limit and one more: expect accept, then reject.
5. Read, update and delete an existing note; read a deleted note: expect not found.
6. List notes with pagination (api.page_size).
7. Archive behaviour: a note is archived after notes.archive_days.
8. Sharing: verify behaviour matches notes.share_mode.
9. Requests without a valid JWT bearer token are rejected.
