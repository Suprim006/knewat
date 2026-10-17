# Acme Notes API - OpenAPI endpoint design (v2)

Built against api_version: v2 (fact 9cb66665-9714-47a5-8948-47f389383f2f).

## Code settings (from repo/api.py)

api.base_path: AX-25930
api.cors_origin: AX-79535

## Changes for v2

- All routes are served under the v2 base path.
- CORS uses the configured api.cors_origin.
- Earlier endpoint designs must be re-based on v2.
