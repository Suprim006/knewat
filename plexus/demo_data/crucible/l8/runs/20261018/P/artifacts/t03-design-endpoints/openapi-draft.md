# Acme Notes API – OpenAPI draft (S21)

Built against API version: v1 (fact bc3d3dc8-479e-4f33-ac4d-79e1347a9c0f)

## Code settings (from repo/api.py)

api.base_path: AX-81436
api.page_size: AX-25149
api.max_body: AX-38941

## Endpoints (under the base path)

- GET    {base_path}/notes        – list notes (paged by page_size)
- POST   {base_path}/notes        – create a note (body limited by max_body)
- GET    {base_path}/notes/{id}   – read a note
- PUT    {base_path}/notes/{id}   – update a note (body limited by max_body)
- DELETE {base_path}/notes/{id}   – delete a note
