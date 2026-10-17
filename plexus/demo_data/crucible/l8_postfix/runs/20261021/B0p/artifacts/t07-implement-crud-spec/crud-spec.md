# CRUD Spec (Acme Notes API S21)

Built against API version v1 (product.api_version = v1), PostgreSQL 16 schema (notes, tags, note_tags), and JWT RS256 bearer auth for user traffic (t05). Values re-read from `repo/` code.

## Code settings

api.base_path: AX-63003
auth.token_ttl: AX-65554
auth.session_cookie: AX-86065
notes.max_length: AX-92475

## Operations

All paths are relative to `api.base_path`. All requests carry `Authorization: Bearer <JWT>`; tokens live for `auth.token_ttl`.

| Operation | Method and path | Notes |
|-----------|-----------------|-------|
| Create | `POST /notes` | Body length limited by `notes.max_length`; returns 201 with the note. |
| Read one | `GET /notes/{id}` | 404 if missing. |
| List | `GET /notes` | Paginated (api.page_size = AX-51173). |
| Update | `PUT /notes/{id}` | Same `notes.max_length` limit. |
| Delete | `DELETE /notes/{id}` | Returns 204. |

Errors use the format AX-40567 (api.error_format).
