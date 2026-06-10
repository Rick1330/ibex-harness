# packages/

Shared libraries and contract artifacts (not deployable as standalone processes).

| Directory | Role |
| --- | --- |
| `proto/` | Protobuf source of truth + buf codegen — [proto/README.md](proto/README.md) |
| `permissions/` | 64-bit permission bitmap ([ADR-0009](../docs/adr/ADR-0009-permission-bitmap.md)) |
| `crypto/` | Approved cryptography — Argon2id PHC, random, constant-time compare ([ADR-0010](../docs/adr/ADR-0010-cryptography-policy.md)) |
| `ratelimit/` | Org-level Redis rate limiting — `Limiter`, `RedisSlider` ([ADR-0015](../docs/adr/ADR-0015-proxy-rate-limit-skeleton.md)) |
| `reqid/` | Request ID generation (UUID v7), context propagation ([ADR-0017](../docs/adr/ADR-0017-request-id-strategy.md)) |
| `shutdown/` | Graceful shutdown coordinator for auth and proxy ([ADR-0018](../docs/adr/ADR-0018-graceful-shutdown.md)) |
| `logger/` | Structured JSON logger with mandatory field schema ([18-observability.mdc](../.cursor/rules/18-observability.mdc)) |
| `telemetry/` | OpenTelemetry tracer/meter init, HTTP span middleware ([ADR-0019](../docs/adr/ADR-0019-opentelemetry-provider-configuration.md)) |
| `metrics/` | Canonical Prometheus metric registry ([ADR-0021](../docs/adr/ADR-0021-prometheus-metric-catalog.md)) |
| `config/` | Typed env loading with aggregated validation ([ADR-0020](../docs/adr/ADR-0020-shared-package-boundaries.md)) |
| `apierror/` | Canonical HTTP/gRPC error codes and envelope ([ADR-0020](../docs/adr/ADR-0020-shared-package-boundaries.md)) |
| `sdk-python/` | Python client SDK (planned) |
| `sdk-typescript/` | TypeScript client SDK (planned) |
| `sdk-go/` | Go client SDK (planned) |
| `cli/` | `ibex` CLI (Go) (planned) |

See [docs/FILE_STRUCTURE.md](../docs/FILE_STRUCTURE.md).
