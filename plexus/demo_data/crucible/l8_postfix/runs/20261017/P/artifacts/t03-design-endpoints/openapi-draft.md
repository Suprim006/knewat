# Acme Notes API - OpenAPI draft (built against API version v1, sprint S21)

## Code settings

api.base_path: AX-25930
api.page_size: AX-73505
api.max_body: AX-78618

## Endpoints (under the base path)

- GET    /notes        - list notes (paginated by page_size)
- POST   /notes        - create a note (body limited by max_body)
- GET    /notes/{id}   - read a note
- PUT    /notes/{id}   - update a note (body limited by max_body)
- DELETE /notes/{id}   - delete a note
