# Acme Notes API - OpenAPI draft (built against API version v1, sprint S21)

## Settings (from repo/api.py)

api.base_path: AX-81436
api.page_size: AX-25149
api.max_body: AX-38941

## Endpoints (under the base path)

- GET    /notes        - list notes (paged by page_size)
- POST   /notes        - create a note (body limited by max_body)
- GET    /notes/{id}   - read a note
- PUT    /notes/{id}   - update a note (body limited by max_body)
- DELETE /notes/{id}   - delete a note
