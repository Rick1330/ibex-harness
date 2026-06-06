# packages/

Shared libraries and contract artifacts (not deployable as standalone processes).

| Directory | Role |
| --- | --- |
| `proto/` | Protobuf source of truth + buf codegen — [proto/README.md](proto/README.md) |
| `permissions/` | 64-bit permission bitmap ([ADR-0009](../docs/adr/ADR-0009-permission-bitmap.md)) |
| `crypto/` | Approved cryptography — Argon2id PHC, random, constant-time compare ([ADR-0010](../docs/adr/ADR-0010-cryptography-policy.md)) |
| `ratelimit/` | Org-level Redis rate limiting — `Limiter`, `RedisSlider` ([ADR-0015](../docs/adr/ADR-0015-proxy-rate-limit-skeleton.md)) |
| `sdk-python/` | Python client SDK (planned) |
| `sdk-typescript/` | TypeScript client SDK (planned) |
| `sdk-go/` | Go client SDK (planned) |
| `cli/` | `ibex` CLI (Go) (planned) |

See [docs/FILE_STRUCTURE.md](../docs/FILE_STRUCTURE.md).
