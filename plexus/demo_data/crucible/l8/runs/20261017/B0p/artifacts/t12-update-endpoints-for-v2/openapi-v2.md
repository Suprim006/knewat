# OpenAPI v2: Acme Notes API (sprint S21)

Built against API version: v2 (style_guide.api_version = v2; decision D-t02-v2, supersedes v1 draft in artifacts/t03-design-endpoints/openapi-draft.md).
Note: the v2 guide file (acme-docs/06_api_style_guide_v2.md) is not in the workspace; v2 changes are taken from the researcher's log entry (routes under /v2/, page_token/page_size, RFC 9457 errors).

## Code settings (from repo/api.py, read this turn)

api.base_path: AX-25930
api.cors_origin: AX-79535

## Endpoints (v2, routes under /v2/ relative to base path AX-25930)

| operation | method | path | notes |
|-----------|--------|------|-------|
| list notes | GET | /v2/notes | paginated with page_token and page_size |
| create note | POST | /v2/notes | |
| read note | GET | /v2/notes/{id} | |
| update note | PUT | /v2/notes/{id} | |
| delete note | DELETE | /v2/notes/{id} | |

## Changes from v1

- Routes move under /v2/.
- Pagination uses page_token / page_size (cursor style).
- Errors use RFC 9457 problem details (replaces v1 error format).
- Auth unchanged: JWT bearer (D-t05).
