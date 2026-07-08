# IBEX Harness — Deployment

## 1) Purpose

This document defines **how IBEX Harness is built, released, deployed, and rolled back** safely.

IBEX Harness has:

- multiple services (Go, Python, TypeScript),
- strict multi-tenancy and security invariants,
- latency-critical paths (proxy + context assembly),
- stateful dependencies (Postgres, Redis, ClickHouse, MinIO),
- and non-trivial migrations (schema + embedding evolution).

A deployment strategy must guarantee:

- **no downtime** for stateless services when possible,
- **safe schema evolution** without breaking older versions,
- **fast rollback** of application code (forward-only DB migrations),
- **observability gates** to detect regressions during rollout,
- **no secret leakage** through CI/CD or Helm values.

---

## 2) Environments

### 2.1 Environment list

| Environment | Purpose | Data | Stability | Who uses it |
|-------------|---------|------|-----------|-------------|
| `local` | dev on laptop | disposable | low | engineers |
| `dev` | shared dev cluster | disposable | low | engineers |
| `staging` | production-like | seeded anonymized data | medium-high | engineers + QA |
| `prod` | production | real customer data | highest | customers |

### 2.2 Invariants by environment

- **prod/staging**: security invariants must be identical (auth, RLS, rate limiting)
- **dev/local**: may use simplified deployments, but must not bypass security invariants
- **local** can run in “mock LLM mode,” but the proxy’s auth + rate limit code paths must still execute.

---

## 3) Deployment Models

### 3.1 SaaS (primary model)

- Kubernetes-managed services
- managed or self-managed DBs depending on cost/compliance
- ArgoCD GitOps for deployments
- Terraform for cloud infra provisioning

### 3.2 Enterprise Self-Hosted (secondary model)

- Kubernetes + Helm delivered to customer
- S3-compatible storage via MinIO
- Postgres/Redis/ClickHouse either customer-managed or bundled charts (configurable)
- external secret integration required (Vault, ExternalSecrets, etc.)

**Requirement:** Our charts must support both SaaS and self-hosted.

---

## 4) Source Control → Artifact → Deployment Flow (High-Level)

### 4.1 “Main is always releasable”

- `main` must remain deployable at all times.
- Every merge to `main` triggers a staging deployment.
- Production deployments occur from tagged releases.

### 4.2 Artifact immutability

- Build produces immutable artifacts (container images + SBOM).
- Deployments reference images by digest (`sha256:...`), not mutable tags.

### 4.3 GitOps principle

- Desired deployment state is declared in Git.
- ArgoCD reconciles cluster state to Git state.
- Rollback is a Git revert + Argo sync.

---

## 5) CI (Build + Test + Security + Artifact Production)

### 5.1 CI triggers

- On `pull_request`: run quality gates (no deployment).
- On merge to `main`: build + publish images + deploy to staging.
- On release tag (e.g., `v1.2.3`): build + publish + deploy to prod with progressive rollout.

### 5.2 Required CI gates (must pass)

**Code quality**

- Go: `golangci-lint`, `go test`, `go test -race` (critical services)
- Python: `ruff`, `mypy`, `pytest`
- TypeScript: `eslint`, `tsc --noEmit`, `vitest`

**Contracts**

- `buf lint`
- `buf breaking` against `main`
- codegen consistency check (fail if generated code differs from committed output policy)

**Security**

- secret scanning (gitleaks)
- dependency vulnerabilities (OSV/Dependabot/Trivy)
- SAST (semgrep baseline rules)
- container image scan (Trivy)

**Tests**

- unit tests always
- integration tests for services that touched DB/cache/queues (detect via path-based CI rules)

### 5.3 Artifact outputs

For each deployable service:

- container image (`ghcr.io/<org>/ibex-<service>:<sha>`)
- image digest pinned in deployment manifests
- SBOM (CycloneDX or SPDX)
- provenance (optional but recommended, e.g., SLSA attestation)

**Rule:** no deployment without security scanning and SBOM generation.

---

## 6) CD (Staging/Prod Promotion Strategy)

### 6.1 Deployment controller

- ArgoCD pulls from Git and applies Helm charts/manifests.
- Environments are separate Argo applications:
  - `ibex-staging`
  - `ibex-prod`

### 6.2 Promotion model

- Merge to `main` → staging deploy automatically
- Production deploys are triggered by:
  - a Git tag `vX.Y.Z` OR
  - a release PR merging `release/<version>` into `main` (team preference)

### 6.3 Progressive delivery strategies (per component)

#### Stateless services (proxy/auth/api/memory/context/embedder/dashboard)

Recommended rollout: **blue/green** or **canary** depending on risk.

**Default: Canary**

- Shift traffic gradually: `5% → 25% → 100%`
- Observe error rate + latency at each step
- Auto-rollback on regression thresholds

**When to use blue/green**

- When compatibility changes are risky
- When you want instant rollback by flipping traffic switch

**Rollback time target:** < 2 minutes for stateless services.

#### Worker service (Celery)

Workers do not serve user traffic directly; they process jobs.
Recommended rollout: **canary workers**

- upgrade 10% of workers first
- monitor task failure rate + DLQ depth
- then upgrade remaining workers

#### Stateful components (Postgres/Redis/ClickHouse/MinIO)

We prefer managed services in SaaS where possible.
If self-managed:

- upgrades are planned maintenance tasks
- rolling restarts only when safe
- backup verification required before any upgrade

---

## 7) Rollback Strategy (What Can and Cannot Be Rolled Back)

### 7.1 Stateless services

- Roll back by reverting Git desired state to previous image digest
- ArgoCD sync applies rollback

### 7.2 Database migrations (forward-only)

**We do not auto-rollback schema migrations.**
Instead:

- schema changes must be backward compatible
- application rollbacks must still work with migrated schema

### 7.3 Expand/Contract migration discipline (mandatory)

To rename a column `old_name → new_name`:

1. Expand: add `new_name` (nullable)
2. Deploy app that writes both `old_name` and `new_name`
3. Backfill data in batches (worker job)
4. Deploy app that reads `new_name` only
5. Contract: drop `old_name` in later release

This is the only safe way to do schema evolution in zero-downtime systems.

---

## 8) Database Migration Procedures (Production Safe)

### 8.1 Migration rules (PostgreSQL)

**Rule A: Additive changes first**

- adding columns/tables/indexes is safe
- dropping/renaming requires a multi-step release plan

**Rule B: Index creation on large tables**

- use `CREATE INDEX CONCURRENTLY` for large tables
- do not block writes

**Rule C: Adding NOT NULL constraints**

- add nullable column first
- backfill in batches
- then add NOT NULL constraint

**Rule D: Foreign keys on large tables**

- add as `NOT VALID` first
- validate later:
  - `ALTER TABLE ... VALIDATE CONSTRAINT ...`

### 8.2 Migration runtime controls

- apply statement timeouts (`POSTGRES_STATEMENT_TIMEOUT_MS`)
- apply lock timeouts to avoid deadlocks
- run heavy backfills via worker jobs, not migrations

### 8.3 Roll-forward fix strategy

If a migration is wrong:

- ship a new migration that fixes it
- do not attempt to roll it back automatically

---

## 9) Deployment Gates (SLO-based)

### 9.1 Canary gate metrics

During rollout, we check:

- error rate delta (service 5xx rate)
- latency delta (p95/p99)
- fallbacks increase (proxy fallback reasons)
- circuit breaker open rate (provider failures)
- queue growth (worker queues if changes affect async pipeline)

**Example automatic rollback triggers**

- error rate increases by > 2% absolute for 10 minutes
- p99 proxy overhead increases by > 20% for 10 minutes
- context assembly p95 exceeds 50ms for 10 minutes
- memory search p95 exceeds 100ms for 10 minutes
- DLQ depth increases above threshold rapidly

### 9.2 “Freeze deploy” conditions

Deployments are paused if:

- suspected tenant isolation issue
- auth bypass suspicion
- billing pipeline integrity issue
- data corruption suspicion

---

## 10) Secrets in Deployment (Never in Git)

### 10.1 Allowed secret delivery mechanisms

- Kubernetes ExternalSecrets Operator (recommended)
- HashiCorp Vault injection
- cloud-native secrets manager (AWS/GCP/Azure)
- sealed secrets (acceptable, but rotation harder)

### 10.2 Forbidden

- secrets in `values.yaml`
- secrets in `values-prod.yaml` committed to git
- secrets in Dockerfile build args
- secrets in CI logs
- secrets in GitHub Actions outputs

### 10.3 Rotation requirements

- service-to-service tokens rotate every 24h with overlap
- JWT signing key rotation requires keysets for verification (current + previous)
- rotation must not require full cluster restart if avoidable

---

## 11) Helm Chart Practices (Staging/Prod)

### 11.1 Values discipline

- `values.yaml` contains safe defaults
- environment overrides in `values-staging.yaml`, `values-prod.yaml`
- secrets referenced via external secret resources, not literal values

### 11.2 Resource requests/limits (mandatory)

Every service must define:

- CPU and memory requests
- CPU and memory limits
- liveness + readiness probes
- graceful termination period

### 11.3 Health probes

- `/health`: liveness, minimal dependencies
- `/ready`: readiness, verifies critical deps (DB/Redis/auth as applicable)

---

## 12) Release Versioning

### 12.1 Version semantics

- Services use semantic versioning (semver)
- Public REST API version in URL (`/v1`)
- Protobuf evolves additively (breaking changes require new package version)

### 12.2 Release tags

- `vX.Y.Z` is a release tag for the platform
- container images are built for each service with:
  - `:vX.Y.Z`
  - `:sha-<gitsha>`
- production should reference digests

---

## 13) Deployment Order (Critical Dependencies)

In environments where everything deploys together:

1. Infrastructure dependencies (if self-hosted):
   - Postgres, Redis, ClickHouse, MinIO
2. Auth service (needed by most services)
3. Memory + Context + Embedder (core platform)
4. Proxy (depends on Auth + Context)
5. Worker service (depends on Memory/Embedder/ClickHouse)
6. API server (management plane)
7. Dashboard

**Important:** Many services can start without their deps (but not be ready).
Readiness probes control routing. Do not “hard fail” startup unless configuration is missing.

---

## 14) Operational Playbooks (Minimum)

### 14.1 Rollback playbook (stateless)

1. Identify last known good image digest
2. Update Git desired state (Helm values or manifest)
3. ArgoCD sync
4. Confirm:
   - error rate back to baseline
   - latency back to baseline
   - fallbacks return to baseline
5. Write incident notes with:
   - rollback reason
   - metrics evidence
   - follow-up issue

### 14.2 Migration playbook

1. Ensure backups are current and verified (restore test periodically)
2. Apply expand migration
3. Deploy app version that dual-writes
4. Backfill with worker job
5. Deploy app version that reads new schema
6. Apply contract migration later

---

## 15) Deployment Verification Checklist

For any production deployment:

- [ ] All CI gates passed
- [ ] SBOM generated and stored
- [ ] Container scans pass (no critical CVEs or explicit exceptions documented)
- [ ] Migrations are backward compatible with rollback code
- [ ] Canary rollout configured
- [ ] Grafana dashboards and alerts updated
- [ ] Runbooks exist for new alerts
- [ ] Post-deploy smoke tests pass:
  - auth token validation
  - memory write/read basic
  - proxy request basic
  - dashboard basic load

---

## 16) Smoke Tests (Post-deploy)

Minimum automated smoke tests:

1. `GET /health` and `GET /ready` for each service
2. Auth: create session token (staging only) and validate
3. Memory: write memory and retrieve it
4. Context: assemble context with minimal query
5. Proxy: proxy a “mock provider” request and confirm:
   - headers preserved
   - context injected
   - trace emitted
6. Worker: enqueue a small job and confirm it completes
7. Dashboard: render agents list (server component path)

---

## 17) What This Document Does NOT Decide

Some deployment choices depend on org preference:

- managed vs self-hosted databases in SaaS
- exact progressive delivery tooling (Argo Rollouts vs native Kubernetes + metrics gate)
- SLSA provenance enforcement strictness
- whether to commit generated proto code vs generate in CI (ADR required)

---

Deployment is a safety system.
If we deploy quickly but unsafely, we are not moving faster —
we are accumulating irreversible risk.
