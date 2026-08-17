# packages/

Shared libraries and contract artifacts (not deployable as standalone processes).

| Directory | Role |
| --- | --- |
| `proto/` | Protobuf source of truth + buf codegen — [proto/README.md](proto/README.md) |
| `permissions/` | 64-bit permission bitmap ([ADR-0009](../web/content/docs/adr/0009-permission-bitmap.mdx)) |
| `crypto/` | Approved cryptography — Argon2id PHC, random, constant-time compare ([ADR-0010](../web/content/docs/adr/0010-cryptography-policy.mdx)) |
| `ratelimit/` | Org-level Redis rate limiting — `Limiter`, `RedisSlider` ([ADR-0015](../web/content/docs/adr/0015-proxy-rate-limit-skeleton.mdx)) |
| `reqid/` | Request ID generation (UUID v7), context propagation ([ADR-0017](../web/content/docs/adr/0017-request-id-strategy.mdx)) |
| `shutdown/` | Graceful shutdown coordinator for auth and proxy ([ADR-0018](../web/content/docs/adr/0018-graceful-shutdown.mdx)) |
| `logger/` | Structured JSON logger with mandatory field schema ([AGENTS.md](../AGENTS.md) §10) |
| `telemetry/` | OpenTelemetry tracer/meter init, HTTP span middleware ([ADR-0019](../web/content/docs/adr/0019-opentelemetry-provider-configuration.mdx)) |
| `metrics/` | Canonical Prometheus metric registry ([ADR-0021](../web/content/docs/adr/0021-prometheus-metric-catalog.mdx)) |
| `config/` | Typed env loading with aggregated validation ([ADR-0020](../web/content/docs/adr/0020-shared-package-boundaries.mdx)) |
| `apierror/` | Canonical HTTP/gRPC error codes and envelope ([ADR-0020](../web/content/docs/adr/0020-shared-package-boundaries.mdx)) |
| `session/` | Session store contract (intentional multi-consumer API — [ARCHITECTURE_LAYERING.md](../web/engineering/ARCHITECTURE_LAYERING.md)) |
| `idempotency/` | Idempotency store contract (intentional multi-consumer API) |
| `directive/` | Directive resolver contract (intentional multi-consumer API) |
| `injection/` | System-prompt injection strategies for chat messages ([ADR-0031](../web/content/docs/adr/0031-system-prompt-injection.mdx)) |
| `authcache/` | Token validation LRU + bloom of invalids ([ADR-0028](../web/content/docs/adr/0028-auth-cache-design.mdx)) |
| `revocation/` | Auth-cache revocation channel helpers ([ADR-0029](../web/content/docs/adr/0029-token-revocation-propagation.mdx)) |
| `redissub/` | Shared Redis SUBSCRIBE helpers for revocation fan-out |
| `healthcheck/` | Shared `/health` and `/ready` probe framework ([ADR-0022](../web/content/docs/adr/0022-health-check-contract.mdx)) |
| `provider/` | LLM provider abstraction and model registry ([ADR-0025](../web/content/docs/adr/0025-llm-provider-abstraction.mdx)) |
| `clickhouse/` | ClickHouse writer/DSN helpers for `llm_traces` ([ADR-0033](../web/content/docs/adr/0033-clickhouse-schema.mdx)) |
| `chdsn/` | ClickHouse DSN flattening helpers |
| `sdk-python/` | Python client SDK (planned) |
| `sdk-typescript/` | TypeScript client SDK (planned) |
| `sdk-go/` | Go client SDK (planned) |
| `cli/` | `ibex` CLI (Go) (planned) |

**TypeScript:** pnpm workspace members with a `package.json` (today `@ibex-harness/proto` for local codegen; future `sdk-typescript/`, shared UI tokens) live alongside Go packages. pnpm ignores directories without `package.json`.

See [web/engineering/FILE_STRUCTURE.md](../web/engineering/FILE_STRUCTURE.md).
