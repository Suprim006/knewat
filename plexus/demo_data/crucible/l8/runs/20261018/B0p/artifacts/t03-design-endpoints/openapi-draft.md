# OpenAPI draft: Acme Notes API S21

Built against API version v1 (decision t02-choose-api-version; facts style_guide.api_version = v1, api.base_path, api.error_format).

## Code settings (from repo/api.py)

api.base_path: AX-81436
api.page_size: AX-25149
api.max_body: AX-38941

## Endpoints (under base path AX-81436)

| operation | method | path | notes |
|-----------|--------|------|-------|
| list notes | GET | AX-81436/notes | paginated, page size AX-25149 |
| create note | POST | AX-81436/notes | body limit AX-38941 |
| read note | GET | AX-81436/notes/{id} | |
| update note | PUT | AX-81436/notes/{id} | body limit AX-38941 |
| delete note | DELETE | AX-81436/notes/{id} | |

Errors use error format AX-90930.
