# Acme Notes API S21 - Test Plan

## Scope
CRUD endpoints for notes (create, read, update, delete, list) and the notes limits.

## API version
The recall for "API version" returned only per-sprint facts (S02 to S19, latest v38 for S19). No S21 API version fact was found, so none is asserted here.

## Code settings under test
notes.max_length: AX-92475
notes.tag_limit: AX-18114
notes.archive_days: AX-25751
notes.share_mode: AX-70519
notes.title_max: AX-63550

## Test cases
- Create: valid note returns success. Title over notes.title_max and body over notes.max_length are rejected.
- Read: existing note is returned. Missing note returns 404.
- Update: fields change. The same limit checks apply as for create.
- Delete: note is removed and a later read returns 404.
- List: returns the notes that exist.
- Tags: adding tags beyond notes.tag_limit is rejected.
- Archive: archiving follows notes.archive_days.
- Sharing: behaviour follows notes.share_mode.
