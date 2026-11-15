# Bundles

A bundle is a supported, tested subset of the platform with explicit limits. It is not a separate service and it does
not get its own version. Bundles are recorded in `release-manifest.json` so a deploy can answer "which subset is this,
and was it smoked?".

## `memory-context`

The memory/context substrate without the LLM proxy:

| Included | Role |
| --- | --- |
| `auth` | Token validation over gRPC |
| `memory` | Memory write, search, feedback, and probes |
| `embedder` | Deterministic `cpu` profile for contract tests and local use |
| PostgreSQL with pgvector | Primary store and vector index |
| Migrations | `infra/migrations` applied by the migrate image |
| Provisioning | One-shot `provision` that sets the capability-login passwords |
| Dev seed | `infra/scripts/seed_dev.sql` for local verification only |

Every application service connects as its own capability login, never the owner `ibex`: `auth` uses `ibex_auth` and
`memory` uses `ibex_runtime`. Both binaries assert this at startup and refuse the RLS-bypassing owner. The migrations
create those roles with `CONNECTION LIMIT 0`, so the `provision` one-shot sets each SCRAM verifier and lifts the limit
before either service starts; `auth` and `memory` wait for it to complete. `migrate` and the dev seed stay on the owner
login, because they are privileged setup steps rather than application traffic.

The capability passwords in this bundle are fixed test values (`bundle-test-auth`, `bundle-test-runtime`,
`bundle-test-worker`, `bundle-test-bootstrap`) for a throwaway local database. They are deliberately not the owner
credential and are pairwise distinct, which is what `provision` enforces. A deployment profile generates real secrets
instead (`infra/compose/v1-single-node`).

Optional: Redis for the hot cache. The base profile runs without it.

### Run it

One-shot verification starts and removes its own stack (`ibex-memory-context-smoke`, port `18005`):

```bash
make bundle-smoke
```

For an interactive stack, use the default project and do not run the smoke against it at the same time:

```bash
docker compose -f infra/compose/bundles/memory-context.yml up -d --build
docker compose -f infra/compose/bundles/memory-context.yml down -v
```

`make bundle-smoke` starts the profile, applies migrations, provisions the capability logins, applies the dev seed,
and then proves:

- migrations are clean at the highest local Postgres version;
- AuthService, embedder, and memory are healthy;
- a benign memory can be created and found by search;
- duplicate content returns `409 DUPLICATE_CONTENT`;
- a missing token returns `401`;
- an agent from another organization is not readable (`403` today; `404` is the preferred code).

The smoke writes `bundle-smoke-result.json` with `bundle`, `status`, `commit`, and `finished_at`. The file is
gitignored.

### Manifest status

`infra/bundles/memory-context.json` declares the bundle. `release-manifest.py` emits it under `bundles`:

- `unverified` by default;
- `smoke-passed` only when `--smoke-results` contains a result for the same bundle, with `status: "passed"`, the same
  commit as the manifest, and a timezone-aware `finished_at`.

A bundle smoke that runs on a different commit does not promote the release. That keeps the manifest honest about what
was actually exercised.

### Upgrade order

1. PostgreSQL with pgvector.
2. Migrations (`migrate up`).
3. Capability-login provisioning (`migrate provision`), which unlocks the capability roles.
4. AuthService.
5. Embedder.
6. Memory.
7. Seed data only in local/test.

### Limits and non-claims

This is a **local supported profile**, not a hosted product.

- No high availability, measured SLO, backup, restore, or production deployment claim.
- The `cpu` embedder profile is deterministic stub geometry. It proves the contract, not semantic retrieval quality.
- No hard budgets without the budget ledger.
- No durable evidence without the outbox and relay.
- No tenant-wide memory without AuthService.
- Exactly-once effects and replay are not claimed.

Retrieval quality, budgets, evidence, and hosted recovery each need their own evidence before this profile can be
described as more than local and supported.

### CI status

The smoke is a local `make` target. Adding it to `.github/workflows/**` requires owner approval under ADR-0089 §6. Until
that job exists and produces a same-commit artifact, the release manifest reports `unverified`.
