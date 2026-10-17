# OpenAPI draft: Acme Notes API S21 (API version v1)

Built against API version v1 (memory/facts.md: product.api_version = v1; decision D-t02).

## Code settings (from repo/api.py)

api.base_path: AX-63003
api.page_size: AX-51173
api.max_body: AX-93646

## Endpoints (under base path AX-63003)

| Operation | Method | Path |
|-----------|--------|------|
| List notes | GET | AX-63003/notes |
| Create note | POST | AX-63003/notes |
| Read note | GET | AX-63003/notes/{id} |
| Update note | PUT | AX-63003/notes/{id} |
| Delete note | DELETE | AX-63003/notes/{id} |

- List is paginated with page size AX-51173.
- Request bodies are limited to AX-93646.
