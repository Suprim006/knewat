# Acme Notes API S21 - OpenAPI draft (built against API version v1)

## Endpoints (under api.base_path)

- GET /notes - list notes (paginated by api.page_size)
- POST /notes - create a note (body limited by api.max_body)
- GET /notes/{id} - read a note
- PUT /notes/{id} - update a note
- DELETE /notes/{id} - delete a note

## Code settings

api.base_path: AX-81436
api.page_size: AX-25149
api.max_body: AX-38941
