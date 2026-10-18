# CRUD Spec (Acme Notes API S21)

Built against API version v1, PostgreSQL 16, and JWT bearer tokens (RS256, 15 minute expiry) for user traffic.
Setting values below were read from the current `repo/` code.

## Code settings

api.base_path: AX-81436
auth.token_ttl: AX-75088
auth.session_cookie: AX-98773
notes.max_length: AX-24538

## Endpoints (v1, under api.base_path)

| Operation | Method and path | Notes |
|-----------|-----------------|-------|
| Create | POST /notes | Body limited by notes.max_length; requires bearer JWT |
| Read | GET /notes/{id} | Requires bearer JWT |
| List | GET /notes | Paginated (api.page_size = AX-25149) |
| Update | PUT /notes/{id} | Body limited by notes.max_length |
| Delete | DELETE /notes/{id} | Requires bearer JWT |

Errors use api.error_format = AX-90930. Storage: tables notes, tags, note_tags (t06).
