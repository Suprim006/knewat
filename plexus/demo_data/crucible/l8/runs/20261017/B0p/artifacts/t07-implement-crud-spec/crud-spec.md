# CRUD spec (t07-implement-crud-spec)

Built against API v1 (style_guide.api_version = v1), PostgreSQL 16, and JWT bearer auth (D-t05). Code setting values were read from `repo/` as it is now.

## Code settings

api.base_path: AX-25930
auth.token_ttl: AX-92098
auth.session_cookie: AX-67390
notes.max_length: AX-21323

## Caveats

- `auth.token_ttl` is AX-92098 in the current `repo/auth.py`. `memory/facts.md` still lists AX-46764 (recorded in t04/t05), so that fact is stale. The code value is used here.
- `auth.session_cookie` no longer exists in the current `repo/auth.py`. AX-67390 is the last value recorded in `memory/facts.md` (t04), and I could not confirm it against the code. Treat it as unverified.
- `auth.key_header` has the same drift: the code has AX-47833, and the facts file has AX-96963.

## Operations (all under api.base_path, bearer JWT required)

| Operation | Method and path | Notes |
|-----------|-----------------|-------|
| Create | POST /notes | Body size limited by api.max_body; text limited by notes.max_length |
| Read one | GET /notes/{id} | |
| List | GET /notes | Paged by api.page_size |
| Update | PUT /notes/{id} | Same limits as create |
| Delete | DELETE /notes/{id} | |

Storage is the `notes`, `tags` and `note_tags` tables from t06. Errors use api.error_format.
