# CRUD spec (t07-implement-crud-spec)

Built against API version v1 (style_guide.api_version = v1), PostgreSQL 16, and JWT bearer auth (RS256) per D-t05.
Code settings were read from the current repo/ files.

## Code settings

api.base_path: AX-80684
auth.token_ttl: AX-59344
auth.session_cookie: AX-25766
notes.max_length: AX-16383

## Operations (all under api.base_path, JWT bearer required)

| Operation | Method and path | Notes |
|-----------|-----------------|-------|
| Create | POST /notes | body limited by notes.max_length |
| Read one | GET /notes/{id} | |
| List | GET /notes | paginated |
| Update | PUT /notes/{id} | body limited by notes.max_length |
| Delete | DELETE /notes/{id} | |

Storage: notes, tags, note_tags tables (see artifacts/t06-write-db-schema/schema.md).
Auth: tokens expire after auth.token_ttl (current code value AX-59344, which supersedes the stale AX-87187).
