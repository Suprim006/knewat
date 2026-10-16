# OpenAPI v2: Acme Notes API S21

Built against API version v2 (fact style_guide.api_version = v2, source acme-docs/06_api_style_guide_v2.md; supersedes v1, whose guide is withdrawn). Code settings re-read from repo/api.py.

## Code settings

api.base_path: AX-18174
api.cors_origin: AX-10863

Note: memory/facts.md records api.cors_origin = AX-20729, but the current repo/api.py returns AX-10863; the current code value is used.

## Changes from the v1 draft (t03)

- Routes now live under /v2/ (per the v2 style guide) in addition to the base path AX-18174.
- The v1 style guide reference is replaced by the v2 guide.
- CORS origin is stated explicitly: AX-10863.
- Operations, pagination (AX-95295), body limit (AX-74907) and error format (AX-29401) are unchanged from the repo/api.py values.

## Endpoints (under /v2/ and base path AX-18174)

| Operation | Method | Path | Notes |
|-----------|--------|------|-------|
| List notes | GET | /v2/AX-18174/notes | Paginated, page size AX-95295 |
| Create note | POST | /v2/AX-18174/notes | Request body limited to AX-74907 |
| Read note | GET | /v2/AX-18174/notes/{id} | |
| Update note | PUT | /v2/AX-18174/notes/{id} | Request body limited to AX-74907 |
| Delete note | DELETE | /v2/AX-18174/notes/{id} | |

Errors use the format AX-29401 (api.error_format).
