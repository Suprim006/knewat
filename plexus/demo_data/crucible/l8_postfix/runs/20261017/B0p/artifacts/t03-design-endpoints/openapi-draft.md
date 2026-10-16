# OpenAPI draft: Acme Notes API (sprint S21)

Built against API version: v1 (style_guide.api_version = v1; decision D-t02).

## Code settings (from repo/api.py)

api.base_path: AX-25930
api.page_size: AX-73505
api.max_body: AX-78618

## Endpoints (under base path AX-25930)

| operation | method | path | notes |
|-----------|--------|------|-------|
| list notes | GET | AX-25930/notes | paginated, page size api.page_size |
| create note | POST | AX-25930/notes | body limited to api.max_body |
| read note | GET | AX-25930/notes/{id} | |
| update note | PUT | AX-25930/notes/{id} | body limited to api.max_body |
| delete note | DELETE | AX-25930/notes/{id} | |

Errors use api.error_format = AX-78362.
