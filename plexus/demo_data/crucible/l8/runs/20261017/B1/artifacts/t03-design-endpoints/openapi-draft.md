# Acme Notes API – OpenAPI draft (sprint S21)

Built against API version: v1

## Settings (from repo/api.py)

api.base_path: AX-25930
api.page_size: AX-73505
api.max_body: AX-78618

## Endpoints (under the base path)

- GET    {base_path}/notes        – list notes (paged by page_size)
- POST   {base_path}/notes        – create a note (body limited by max_body)
- GET    {base_path}/notes/{id}   – read a note
- PUT    {base_path}/notes/{id}   – update a note (body limited by max_body)
- DELETE {base_path}/notes/{id}   – delete a note
