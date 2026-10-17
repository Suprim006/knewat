# Acme Notes API – OpenAPI draft (S21, API version v1)

## Endpoints (under api.base_path)

- GET    /notes        – list notes (paged by api.page_size)
- POST   /notes        – create a note (body limited by api.max_body)
- GET    /notes/{id}   – read a note
- PUT    /notes/{id}   – update a note
- DELETE /notes/{id}   – delete a note

## Code settings (from repo/api.py)

api.base_path: AX-18174
api.page_size: AX-95295
api.max_body: AX-74907
