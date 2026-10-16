# Acme Notes API – OpenAPI draft (built against API version v1, sprint S21)

## Endpoints (under the base path)
- GET    /notes        – list notes
- POST   /notes        – create a note
- GET    /notes/{id}   – read a note
- PUT    /notes/{id}   – update a note
- DELETE /notes/{id}   – delete a note

## Code settings (from repo/api.py)
api.base_path: AX-25930
api.page_size: AX-73505
api.max_body: AX-78618
