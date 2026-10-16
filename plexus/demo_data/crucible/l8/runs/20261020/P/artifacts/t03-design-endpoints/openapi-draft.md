# Acme Notes API - OpenAPI draft (S21)

Built against API version: v1

## Code settings (from repo/api.py)

api.base_path: AX-18174
api.page_size: AX-95295
api.max_body: AX-74907

## Endpoints (under the base path)

- GET /notes - list notes (paged by page_size)
- POST /notes - create a note (body limited by max_body)
- GET /notes/{id} - read a note
- PUT /notes/{id} - update a note (body limited by max_body)
- DELETE /notes/{id} - delete a note
