# Infra note: where the Notes API runs

From the Acme infrastructure team.

- Database: PostgreSQL 16 (managed). One schema per service.
- Runtime: a container on the shared Kubernetes cluster, listening on port 8080.
- Configuration comes from environment variables; secrets from the cluster secret store.
- Logs are structured JSON on stdout.
