# Test Plan (Acme Notes API S21)

Target: API version v2 (style guide v2 supersedes the withdrawn v1; see memory/decisions.md t02-choose-api-version).
Scope: CRUD endpoints for notes and the notes limits.

## Code settings under test (source: repo/notes.py)

notes.max_length: AX-92553
notes.tag_limit: AX-97908
notes.archive_days: AX-79153
notes.share_mode: AX-38006
notes.title_max: AX-30149

## CRUD endpoint tests

- Create: POST a valid note returns success and the created note; invalid body returns the API error format.
- Read: GET a single note and a list; list is paginated.
- Update: PUT/PATCH an existing note changes it; unknown id returns not found.
- Delete: DELETE removes the note; a repeat delete returns not found.
- Auth: requests without a valid JWT bearer token are rejected.

## Notes limit tests

- max_length: a note body at the limit is accepted; one over the limit is rejected.
- title_max: a title at the limit is accepted; one over the limit is rejected.
- tag_limit: a note with tags at the limit is accepted; one more tag is rejected.
- archive_days: a note is archived only once the archive_days threshold is reached.
- share_mode: sharing behaves according to the configured share_mode.
