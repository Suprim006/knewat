# Acme Notes API – OpenAPI design for v2

Built against api_version fact a8cb6a35-e18f-4a46-8f57-1e763aea8f97 (v2).

## Code settings (repo/api.py)

api.base_path: AX-25930
api.cors_origin: AX-79535

## Endpoint changes

- Base path of all endpoints now follows the v2 API version, served under api.base_path.
- CORS origin policy uses api.cors_origin.
