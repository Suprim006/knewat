# OpenAPI draft: Acme Notes API S21

Built against API version v1 (style guide acme-docs/02_api_style_guide_v1.md). Values re-checked against repo/api.py.

## Code settings

api.base_path: AX-18174
api.page_size: AX-95295
api.max_body: AX-74907

## Endpoints (all under base path AX-18174)

| Operation | Method | Path | Notes |
|-----------|--------|------|-------|
| List notes | GET | AX-18174/notes | Paginated, page size AX-95295 |
| Create note | POST | AX-18174/notes | Request body limited to AX-74907 |
| Read note | GET | AX-18174/notes/{id} | |
| Update note | PUT | AX-18174/notes/{id} | Request body limited to AX-74907 |
| Delete note | DELETE | AX-18174/notes/{id} | |

Errors use the format AX-29401 (api.error_format).
