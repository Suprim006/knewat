# OpenAPI draft: Acme Notes API (sprint S21)

Built against API version v1 (facts: style_guide.api_version = v1; decision D-t02).

## Code settings (read from repo/api.py)

api.base_path: AX-80684
api.page_size: AX-48354
api.max_body: AX-44971

## Endpoints (under base path AX-80684)

| Operation | Method | Path | Notes |
|-----------|--------|------|-------|
| List notes | GET | AX-80684/notes | paged, page size api.page_size |
| Create note | POST | AX-80684/notes | body limit api.max_body |
| Read note | GET | AX-80684/notes/{id} | |
| Update note | PUT | AX-80684/notes/{id} | body limit api.max_body |
| Delete note | DELETE | AX-80684/notes/{id} | |
