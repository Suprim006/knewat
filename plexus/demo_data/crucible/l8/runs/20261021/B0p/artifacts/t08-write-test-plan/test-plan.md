# Test Plan (Acme Notes API S21, API v2)

API version under test: v2 (source: memory/facts.md product.api_version; style guide acme-docs/06_api_style_guide_v2.md).

## Code settings (from repo/notes.py)

notes.max_length: AX-92475
notes.tag_limit: AX-18114
notes.archive_days: AX-25751
notes.share_mode: AX-70519
notes.title_max: AX-63550

## Scope

CRUD endpoints for notes and the notes limits above.

## CRUD test cases

1. Create: POST a valid note returns success and the created note; verify title and body are stored.
2. Read: GET a single note by id returns it; GET an unknown id returns an error in the API error format.
3. List: GET the collection returns notes, respecting pagination.
4. Update: PUT/PATCH changes title, body or tags; verify the stored values change.
5. Delete: DELETE removes the note; a following GET fails.
6. Auth: requests without a valid JWT bearer token are rejected.

## Limit tests

- Title at exactly notes.title_max accepted; one over rejected.
- Body at exactly notes.max_length accepted; one over rejected.
- Tags at exactly notes.tag_limit accepted; one over rejected.
- Notes older than notes.archive_days are archived; younger notes are not.
- Sharing behaves according to notes.share_mode.
