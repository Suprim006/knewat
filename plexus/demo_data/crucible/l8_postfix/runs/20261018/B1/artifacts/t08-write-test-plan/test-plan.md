# Test Plan: Acme Notes API S21 (API version v2)

## Scope
- CRUD endpoints for notes (create, read, update, delete, list)
- Notes limits (length, tags, title, archiving, sharing)

## Code settings under test
notes.max_length: AX-24538
notes.tag_limit: AX-19959
notes.archive_days: AX-87154
notes.share_mode: AX-39123
notes.title_max: AX-89547

## Test cases
1. Create a note within limits returns success; exceeding notes.max_length or notes.title_max is rejected.
2. Read and list return created notes under API v2.
3. Update respects notes.max_length, notes.title_max and notes.tag_limit.
4. Delete removes the note; subsequent read fails.
5. Notes older than notes.archive_days are archived.
6. Sharing behaves according to notes.share_mode.
