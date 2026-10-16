# Acme Notes API Test Plan (S21)

## Scope
- CRUD endpoints for notes: create, read, update, delete, list.
- Notes limits: length, tags, archive window, sharing, title size.

## Code settings under test
notes.max_length: AX-16383
notes.tag_limit: AX-60457
notes.archive_days: AX-94273
notes.share_mode: AX-43223
notes.title_max: AX-40109

## Test cases
1. Create a note at and just over `notes.max_length`; expect accept / reject.
2. Create a note with a title at and over `notes.title_max`.
3. Attach tags up to and beyond `notes.tag_limit`.
4. Archive behaviour around `notes.archive_days`.
5. Sharing behaviour according to `notes.share_mode`.
6. Read, update, delete, and list round trips; 404 on missing notes.

## Notes
- The recall for "API version" returned per-sprint facts only; no S21 API version was found, so none is stated here.
