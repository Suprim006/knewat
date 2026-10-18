# OpenAPI v2: Acme Notes API S21 (API version v2)

Built against API version v2 (memory/facts.md: product.api_version = v2, from acme-docs/06_api_style_guide_v2.md; supersedes v1 used in t03; decision D-t02 update).

## Code settings (re-read from repo/api.py)

api.base_path: AX-63003
api.cors_origin: AX-94293

## Endpoints (routes under /v2/ per the v2 style guide, on base path AX-63003)

| Operation | Method | Path |
|-----------|--------|------|
| List notes | GET | /v2/notes |
| Create note | POST | /v2/notes |
| Read note | GET | /v2/notes/{id} |
| Update note | PUT | /v2/notes/{id} |
| Delete note | DELETE | /v2/notes/{id} |

## Changes from the v1 draft (t03)

- Routes are versioned under /v2/.
- List pagination uses page_token / page_size query parameters.
- Errors use RFC 9457 problem details.
- CORS origin setting is AX-94293.
