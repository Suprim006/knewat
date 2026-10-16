# Acme Notes API - OpenAPI draft (built against API version v1)

## Endpoints (under the base path)
- GET    {base_path}/notes        - list notes (paginated by page_size)
- POST   {base_path}/notes        - create a note (body limited by max_body)
- GET    {base_path}/notes/{id}   - read a note
- PUT    {base_path}/notes/{id}   - update a note
- DELETE {base_path}/notes/{id}   - delete a note

## Code settings
api.base_path: AX-18174
api.page_size: AX-95295
api.max_body: AX-74907
