# Acme Notes API S21 - OpenAPI draft

Built against API version: v1 (fact ee47d116-9952-40ad-879c-0e63e88f166a).

## Endpoints (under the base path)
- GET    {base_path}/notes        - list notes (paged by page_size)
- POST   {base_path}/notes        - create a note (body up to max_body)
- GET    {base_path}/notes/{id}   - read a note
- PUT    {base_path}/notes/{id}   - update a note
- DELETE {base_path}/notes/{id}   - delete a note

## Code settings (from repo/api.py)
api.base_path: AX-63003
api.page_size: AX-51173
api.max_body: AX-93646
