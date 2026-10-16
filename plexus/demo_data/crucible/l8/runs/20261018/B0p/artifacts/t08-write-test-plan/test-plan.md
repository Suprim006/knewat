# Test Plan (Acme Notes API S21)

API version under test: v2 (per style guide 06_api_style_guide_v2.md; v1 is withdrawn). Routes use the `/v2/` prefix.

## Scope
- CRUD endpoints for notes (create, read, update, delete, list)
- Notes limits (length, tags, title, archive, share)

## Code settings under test
notes.max_length: AX-24538
notes.tag_limit: AX-19959
notes.archive_days: AX-87154
notes.share_mode: AX-39123
notes.title_max: AX-89547

## Test cases
1. Create a note at exactly the notes.max_length limit: accepted; one beyond: rejected.
2. Create a note with a title at notes.title_max: accepted; one beyond: rejected.
3. Add tags up to notes.tag_limit: accepted; one more: rejected.
4. Read, update and delete an existing note; unknown id returns an error in the API error format.
5. List notes with pagination (api.page_size).
6. Archive behaviour after notes.archive_days.
7. Sharing behaves according to notes.share_mode.
8. Requests without a valid JWT bearer token are rejected.
