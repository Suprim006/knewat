# Acme Notes API - OpenAPI draft (built against API version v1)

## Endpoints (under api.base_path)

- GET    {base_path}/notes        - list notes (paged by api.page_size)
- POST   {base_path}/notes        - create a note (body limited by api.max_body)
- GET    {base_path}/notes/{id}   - read a note
- PUT    {base_path}/notes/{id}   - update a note
- DELETE {base_path}/notes/{id}   - delete a note

## Code settings (from repo/api.py)

api.base_path: AX-63003
api.page_size: AX-51173
api.max_body: AX-93646
