# infra/

Deployment, local development infrastructure, and observability configuration.

Planned layout (see [web/engineering/FILE_STRUCTURE.md](../web/engineering/FILE_STRUCTURE.md)):

| Directory | Role |
| --- | --- |
| `compose/dev/` | Docker Compose for local dependencies |
| `compose/test/` | Compose for CI/integration tests |
| `docker/` | Shared Docker build assets |
| `helm/` | Kubernetes Helm charts |
| `terraform/` | Cloud infrastructure as code |
| `monitoring/` | Prometheus, Grafana, Loki, Tempo configs |
| `scripts/` | Operational helpers |

**Available now:**

- `compose/dev/` — [compose/dev/README.md](compose/dev/README.md) (Postgres, Redis Stack, ClickHouse, MinIO)
- `compose/test/` — minimal Postgres + Redis for future integration tests

Other infra (helm, terraform, monitoring) is not implemented yet.
