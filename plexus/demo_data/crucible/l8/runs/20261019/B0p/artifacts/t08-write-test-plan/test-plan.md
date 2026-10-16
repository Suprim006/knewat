# Test Plan (Acme Notes API S21)

API version under test: v2 (source: memory/facts.md, style_guide.api_version; v1 guide withdrawn).

## Scope

- CRUD endpoints for notes (create, read, update, delete, list), as designed in t03 and updated for v2 in t12.
- Notes limits, using the code settings below.

## Code settings under test

notes.max_length: AX-16383
notes.tag_limit: AX-60457
notes.archive_days: AX-94273
notes.share_mode: AX-43223
notes.title_max: AX-40109

(source: repo/notes.py)

## CRUD test cases

1. Create: POST a valid note returns 201 and the stored note.
2. Read: GET an existing note returns 200; an unknown id returns 404 in the API error format.
3. Update: PUT/PATCH an existing note changes only the given fields.
4. Delete: DELETE removes the note; a later GET returns 404.
5. List: GET the collection is paginated and respects the page size.
6. Auth: requests without a valid JWT bearer token are rejected with 401.

## Limit test cases

1. Body length: a note body of notes.max_length is accepted; one past it is rejected.
2. Title length: a title of notes.title_max is accepted; one past it is rejected.
3. Tags: a note with notes.tag_limit tags is accepted; one more tag is rejected.
4. Archive: notes older than notes.archive_days are archived as configured.
5. Sharing: sharing behaves according to notes.share_mode.
