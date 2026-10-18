# Acme Notes API - OpenAPI draft (sprint S21)

Built against API version: v1 (fact 2ff634ee-f426-46b8-90a8-7674f2e0dc00).

## Code settings

api.base_path: AX-80684
api.page_size: AX-48354
api.max_body: AX-44971

## Endpoints (under api.base_path)

- GET /notes - list notes (paged by api.page_size)
- POST /notes - create a note (body limited by api.max_body)
- GET /notes/{id} - read a note
- PUT /notes/{id} - update a note
- DELETE /notes/{id} - delete a note
