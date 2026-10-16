# OpenAPI v2: Acme Notes API S21

Built against API version v2 (fact style_guide.api_version = v2, from acme-docs/06_api_style_guide_v2.md; supersedes v1 used in t03). Decision: t02-choose-api-version (adopt-v2).

## Code settings (from repo/api.py, re-read for this task)

api.base_path: AX-81436
api.cors_origin: AX-84987

Note: memory/facts.md still lists api.cors_origin = AX-17341 (from t01); the current code returns AX-84987, so the code value is used here.

## Endpoints (v2 routes live under /v2/, per the researcher's ingest-v2 log entry)

| operation | method | path | notes |
|-----------|--------|------|-------|
| list notes | GET | /v2/notes (base path AX-81436) | paginated, page size AX-25149 |
| create note | POST | /v2/notes | body limit AX-38941 |
| read note | GET | /v2/notes/{id} | |
| update note | PUT | /v2/notes/{id} | body limit AX-38941 |
| delete note | DELETE | /v2/notes/{id} | |

Errors use error format AX-90930. Cross-origin requests allowed from origin AX-84987.

## What changes from the v1 design (t03)

- Routes move from the v1 layout to the /v2/ prefix.
- CORS origin is stated explicitly (AX-84987).
- Page size, body limit and error format are unchanged in code.
- The v2 style guide text was not available to me; only the /v2/ prefix change is confirmed, via the log.
