# Acme Notes API - OpenAPI draft (endpoints)

Built against API version: v40 (latest recalled fact, Acme Notes API S20 api_version).

## Code settings (repo/api.py)

api.base_path: AX-80684
api.page_size: AX-48354
api.max_body: AX-44971

## Endpoints (relative to api.base_path)

- GET    {base_path}/notes        - list notes (paged by api.page_size)
- POST   {base_path}/notes        - create a note (body limited by api.max_body)
- GET    {base_path}/notes/{id}   - read a note
- PUT    {base_path}/notes/{id}   - update a note
- DELETE {base_path}/notes/{id}   - delete a note
