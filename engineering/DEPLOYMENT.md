# IBEX Harness — Deployment

> **Architecture v2 notice (2026-10-03):** The canonical target architecture, status vocabulary, authority matrix, contract registry, failure semantics, memory lifecycle, evidence model, and implementation gates live in [`engineering/architecture-v2/README.md`](architecture-v2/README.md). This document remains useful for its detailed subject matter, but any conflicting topology, status, SLO, fallback, or production-readiness claim is superseded by architecture-v2 until reconciled through an ADR.

## 1) Purpose

This document defines **how IBEX Harness is built, released, deployed, and rolled back** safely.

**Current shipped surface:** `proxy` + `auth` (+ shared packages/infra), as verified by the baseline. Later services (`embedder`, `memory`, `context`, `worker`, `api`, `console`, `mcp-memory`, optional `tokenizer-service`) follow the redesigned phase sequence in [`engineering/roadmap-archive/legacy-roadmap/`](roadmap-archive/legacy-roadmap/) and [`services/README.md`](../services/README.md). Do not assume every service listed below is deployed today.

IBEX Harness has (target topology):

- multiple services (Go, Python, TypeScript),
- strict multi-tenancy and security invariants,
- latency-critical paths (proxy + context assembly),
- stateful dependencies (Postgres, Redis, ClickHouse, MinIO),
- and non-trivial migrations (schema + embedding-profile evolution).

A deployment strategy must guarantee:

- **no downtime** for stateless services when possible,
- **safe schema evolution** without breaking older versions,
- **fast rollback** of application code (forward-only DB migrations),
- **observability gates** to detect regressions during rollout,
- **no secret leakage** through CI/CD or Helm values.

---

## 1.1 IBEX Console runtime and evidence boundary

`services/console` is the canonical authenticated operator application. `site/` is the public documentation site. The baseline does not verify an IBEX Console package, workload, ingress, hostname, deployment workflow, or production artifact; those must not be inferred from this target deployment document.

The runtime owner must approve either (a) a versioned console static artifact/workload with an explicitly owned BFF/API/SSE topology, or (b) a time-boxed transition runtime. The owner must also define secure cookies, CSRF, exact credentialed CORS when cross-origin, security headers, authenticated SSE drain, and default `Cache-Control: no-store` for personalized/RSC/API/export responses. The API owns context, overview, platform-health, and events truth; console owns presentation and server-only DAL/BFF composition, not authorization or evidence.

Staging promotion is an authenticated browser promotion gate for the IBEX Console artifact. It must include OpenAPI snapshot/generated-client/runtime validation, four-role/two-tenant contract and browser checks, accessibility, visual, hostile-content, cache, SSE, and performance gates, plus immutable artifact and rollback evidence. No public-docs smoke test is equivalent.

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

### 3.3 `v1-single-node` supported profile

ADR-0097 selects **one** v1.0 deployment profile: a single-node, self-hosted Docker Compose project. It is the only
profile a 1.0 claim may cite. Kubernetes, Helm and HA are outside the profile (§10 of the ADR).

**One operator entry point.** `make v1-secrets` generates `infra/compose/v1-single-node/.env` (mode `0600`), the
files under `infra/compose/v1-single-node/secrets/` (directory `0700`; the container copies are `0444` so uid 10001 can
read them), and the `bootstrap/` directory (`0700`) that receives the one-time admin PAT. The `.env` also carries the
four capability-login passwords `IBEX_RUNTIME_DB_PASSWORD`, `IBEX_AUTH_DB_PASSWORD`, `IBEX_WORKER_DB_PASSWORD` and
`IBEX_BOOTSTRAP_DB_PASSWORD`; `migrate provision` is their only writer. `make v1-up` rebuilds the
application images, starts the profile, waits until every required service reports healthy (up to TEI's two-hour
first-start window; override with `IBEX_V1_HEALTH_ATTEMPTS`), and prints the URL plus the PAT hint. `make v1-down` stops it without deleting volumes; `make v1-migrate` re-runs the one-shot migration
service and `make v1-provision` re-runs the one-shot capability-login provisioning service; `make v1-logs` and
`make v1-ps` are the operator inspection commands.

**Three one-shots, in start order: `migrate`, `provision`, `bootstrap`.** `provision` runs `migrate provision` from the
same `infra/migrations/Dockerfile` and the same owner DSN as `migrate`. In one transaction it writes one SCRAM verifier
per capability login — `ibex_runtime`, `ibex_auth`, `ibex_worker` and `ibex_bootstrap`, which the migrations create
inert with no password and `CONNECTION LIMIT 0` — and lifts that connection limit. It reads the four secrets from the
profile `.env` and fails the transaction when one is missing, not printable ASCII without spaces, not pairwise
distinct, or equal to the owner credential, because credential reuse would silently collapse two roles into one. It
then asserts the postcondition before committing: every one of the four is a non-superuser login with `NOBYPASSRLS`,
`NOINHERIT`, `NO CREATEDB`, `NO CREATEROLE`, `CONNECTION LIMIT -1` and no expired validity; `ibex_runtime` and
`ibex_auth` reach `ibex_app`, `ibex_worker` reaches `ibex_app` and `ibex_purge`, `ibex_bootstrap` reaches nothing, and
every login is refused any role it does not require (`ibex_service`, `ibex_purge`, `ibex_bootstrap`, `ibex_auth`). A
stray `GRANT` fails provisioning instead of widening a login. `bootstrap` (the identity one-shot) runs last.

**A failed `provision` is a half-up profile, by design.** `bootstrap`, `auth`, `proxy`, `api`, `memory` and `worker`
wait on `provision` completing rather than on `migrate` alone, so a non-zero exit leaves Postgres, Redis, the edge, the
`migrate` one-shot and the console up — the published port is listening and the console has no upstream — while none
of the six gated services started. That is the safe half: no request is answered and there is no partial identity. It
is also the confusing half, because the datastores report healthy while the profile does nothing; read `make v1-ps`
for the `provision` exit code before reading any other service's state. `make v1-provision` rebuilds the one-shot's
image and re-runs it, honouring `depends_on`, so the credential write is repaired without a teardown.

**Every application service connects on its capability login.** The profile's six application DSNs name the login
directly: `bootstrap` uses `ibex_bootstrap` (`:268`), `auth` uses `ibex_auth` (`:306`), `proxy`, `api` and `memory` use
`ibex_runtime` (`:349`, `:405`, `:452`), and `worker` uses `ibex_worker` (`:548`). Each long-running service asserts the connection
login at startup and refuses to run on the owner or a superuser, so a DSN that authenticates successfully on the wrong
identity fails the start rather than opening an unfiltered read: `services/proxy/internal/bootstrap/postgres.go`:280-306,
`services/auth/cmd/auth/login.go`:57-84, `services/api/app/db.py`:46-80,
`services/memory/app/capability_login.py`:41-72, `services/worker/app/db.py`:112-148. Only `migrate` (`:209`) and
`provision` (`:239`) keep the owner DSN, because provision writes each capability role's password and migrations create
cluster-global roles. Row-level security therefore applies to every application statement.

Live-proven on 2026-11-15: all 13 health-checked containers came up healthy, no application connection is `ibex`, an
unpinned cross-tenant read on `ibex_runtime` raises SQLSTATE `42501`, and a route-level cross-tenant request returns
403. That is a live cross-tenant read plus the integration suites — not a full acceptance suite, and not a two-tenant
browser journey (`P0-21`, `P2-07`). `make repo-guards` runs `infra/scripts/check-tenant-pin.py`, which fails a tracked
Go or Python file that writes `app.current_org_id` without also pinning a tenant role (`SET LOCAL ROLE`, or
`packages/pgtenant.PinOrg`).

**One published port.** The Compose project publishes only the edge HTTPS port (`${IBEX_EDGE_PORT:-443}:8443`; rootless
runtimes should set `IBEX_EDGE_PORT=8443`). Datastores, AuthService, context, memory, worker and MCP ports stay on the
internal bridge. The edge returns `404` for `/health`, `/ready` and `/metrics`; the service-specific readiness checks
(auth: Postgres+gRPC; proxy: AuthService+Redis; API: AuthService+Postgres; memory; embedder/TEI; worker ledger, broker
and consumer; console API health; context gRPC health) are reachable only inside the project. Context has no HTTP
`/ready` endpoint — its readiness signal is the gRPC health service. The profile's service table in the deployment
guide lists each check.

**Component matrix and pins.** `services/{auth,proxy,api,memory,context,embedder,worker,console}` plus the one-shot
`migrate`, `provision` and `bootstrap` services, `pgvector/pgvector:0.8.6-pg16@sha256:ccc6e83d…`, `redis:7.4.2@sha256:fbdbaea4…`,
TEI `ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.4@sha256:2538ea1c…` serving `BAAI/bge-m3` at revision
`5617a9f61b028005a4858fdac845db406aefb181` (1024 dimensions), and the edge terminator
`caddy:2.11.9-alpine@sha256:0bbb055b…`. The first start is gated on TEI: it downloads roughly 2.3 GB into the
`tei-cache` volume and the health window is two hours, because a slow host must not be marked unhealthy mid-download.
The volume persists a partial fetch, so re-running `make v1-up` resumes it; a warm volume is the recommended pre-seed
for an offline or bandwidth-limited install. The reference sizing is a 16 GB host: TEI uses about 8 GB RSS with the
2048-token batch and the application plane about 3 GB. The edge shares one network namespace with the proxy, API,
console, and context, so the browser-credential hops are loopback plaintext and never cross the Compose bridge;
AuthService gRPC carries TLS 1.2+ with the per-install CA. Context binds `127.0.0.1:9092` in that namespace and the
profile bounds assembly at 2 s on both sides because CPU TEI query embedding cannot fit the 45 ms development default.
The proxy verifies signed policy snapshots with the generated `policy_public_keys.json` (key id `v1`); staging and
production refuse to mount protected routes without a verifier. Internal shared-token HTTP and the Redis password on
the host-local bridge are recorded limitations, not a public interface.

**Identity bootstrap.** The one-shot `bootstrap` service creates the organization, owner user, default agent, allow-all
model policy and the memory service token in one transaction, then writes the admin PAT to the host bind mount
`infra/compose/v1-single-node/bootstrap/` (directory `0700`, file `0600`; inside the container `/run/ibex/bootstrap.pat`).
Retrieve it with `make v1-bootstrap-pat`, store it, then delete the file. It is written once, never to the logs or to
the process output, stored only as an Argon2id hash, and is not recoverable. `IBEX_BOOTSTRAP_PAT_FILE` is required
for a first install, so the command cannot fall back to printing the credential. The memory token is a separate
scoped `service_token` (`MemoryRead|MemoryWrite`) used by context and worker; reconciliation binds it to an active
owner and agent and fails closed when either is missing. The committed `seed_dev.sql` token is **not** used.

**Posture.** The tracked `infra/compose/v1-single-node/.env.example` defaults to `IBEX_ENV=staging` + `IBEX_LLM_MODE=mock` so the
profile starts on a clean host without an external LLM. The supported deployment posture is `IBEX_ENV=production` +
`IBEX_LLM_MODE=live` with an operator-supplied provider key or self-hosted LLM; the example carries the commented
production block. The mock LLM is a deterministic fixture, not a production provider.

**Exclusions (verbatim from ADR-0097 §10).** Kubernetes, Helm and any HA topology; hosted or measured SLOs; response-bound
evidence acknowledgement; the run envelope as a runtime artifact; `DecisionService`; MCP writes; the platform-tier
Console surfaces; ClickHouse and MinIO/S3 projections, the reranker, and the observability stack (optional, default
off); multi-user authentication.

**Upgrade and rollback.** Upgrade is a stop-the-stack operation: stop the stack, take a database snapshot, run the
one-shot migration and provisioning services, then start the new images by digest. Rollback restores the snapshot and
starts the previous digests. Migrations are forward-only: starting an older image against the migrated schema is not a
supported rollback. The capability verifiers live in the database (`pg_authid`), so a restore reverts them to their
snapshot state: a start after a restore must let `provision` run again — `make v1-up` does — before a service
authenticates with a credential rotated after that snapshot.

#### Backup and point-in-time recovery (pgBackRest)

The profile's Postgres image is built from `infra/compose/v1-single-node/postgres/Dockerfile` (base
`pgvector/pgvector:0.8.6-pg16` pinned by digest) and adds `pgbackrest` 2.60.0, so the archive command and every base
backup run inside the cluster container where the data directory is. The Compose service is
`image: ibex-v1-postgres:local`; the upstream digest is repeated in a comment above the service so the pin stays visible
from the Compose file.

**Continuous WAL archiving.** Postgres starts with `wal_level=replica`, `archive_mode=on`, `archive_timeout=60` and
`archive_command=pgbackrest --config=/etc/pgbackrest/pgbackrest.conf --stanza=ibex-main archive-push %p`.
`restore_command` is deliberately not set on the running server: recovery parameters exist only for the duration of a
restore, where pgBackRest writes them into `postgresql.auto.conf`. The stanza sets `archive-async=n`: a failed push must
block WAL recycling so the failure is visible in `pg_stat_archiver` instead of being retried behind the server's back.
The cost is that a repository outage retains WAL in `pg_wal` (see the risk note below).

**Repository.** `repo1` is an S3-compatible store at `http://objectstore:9000`, bucket `ibex-pgbackrest`, path-style
addressing, AES-256-CBC repository cipher, `repo1-retention-full=2`. The `objectstore` service is MinIO — Chainguard's
build, pinned by digest (`cgr.dev/chainguard/minio:latest@sha256:bd014394a80898e68c149f2311fdf8d5a2c2f3bb2c33b9327ae6d02b4b065ae1`),
the same pin the dev stack uses. It is not the upstream image because MinIO stopped publishing community images to Docker
Hub and Quay, so no upstream image can be pulled, let alone pinned. Two one-shots gate it: `objectstore-volume-init`
chowns the data volume to the image's uid 65532 before the server starts, and `objectstore-init` creates the bucket with
`mc mb --ignore-existing` and verifies it. MinIO allocates object storage on write and does not preallocate a repository
file per volume, so the data volume holds only what the backups contain. The stanza config is vendor-neutral: pointing
`repo1-s3-endpoint` at any other S3-compatible deployment changes nothing else in the profile. This store is the backup
repository, not the S3 projection excluded by ADR-0097 §10 — the owner should confirm that reading against the ADR.
`ibex-sessions` is not created because no service in this profile sets the worker's `S3_*` variables, so the worker never
writes to object storage.

**Config and credentials are separate.** `make v1-secrets` writes `infra/backup/pgbackrest/pgbackrest.conf` (mode `0644`,
no secrets) and adds `IBEX_OBJECTSTORE_ACCESS_KEY`, `IBEX_OBJECTSTORE_SECRET_KEY` and `PGBACKREST_REPO1_CIPHER_PASS` to
the `0600` `.env`. The directory containing the config is bind-mounted read-only at `/etc/pgbackrest` in the postgres
container, which runs as uid 999: mounting the directory rather than the single file means a regenerated config (the
generator replaces the file with `mv -f`) is visible to a running container instead of leaving it pinned to the old inode.
The config must be world-readable and must therefore carry no secret; Compose passes the three credentials as
`PGBACKREST_REPO1_S3_KEY`, `PGBACKREST_REPO1_S3_KEY_SECRET` and `PGBACKREST_REPO1_CIPHER_PASS` in the container
environment. The generated config is a build artifact, not source: regenerate it with `make v1-secrets` and keep it out of
version control. A custom `PGBACKREST_CONF` is mounted by the restore at the in-container path; the backup path execs into
the running container, so it refuses a config that does not match the container's copy rather than reporting a backup
against a repository the restore will not read. `--force` preserves `PGBACKREST_REPO1_CIPHER_PASS`; rotating it is the
explicit `--rotate-pgbackrest-cipher` operation, and it is refused while a value exists because the old passphrase is the
only key to the existing backups.

**Stanza initialisation.** `stanza-create` is idempotent. `make v1-up` runs it soft after the health wait, so a repository
outage prints a loud warning and leaves the profile serving instead of blocking startup; `make v1-backup-init` is the
strict form that fails instead.

| Command | What it does |
|---|---|
| `make v1-backup` (`TYPE=full` default) | Full backup; `TYPE=diff`, `TYPE=incr`, `TYPE=check` for the others |
| `make v1-backup-init` | Create/verify the stanza and repository; fails loudly if archiving cannot be armed |
| `make v1-restore` | Restore the newest backup over the live volume; stops Postgres, restores with `--delta`, then starts and verifies the cluster |
| `make v1-pitr TARGET=<ISO8601>` | Restore to a timestamp (`--type=time --target-action=promote`); same stop/verify sequence as `v1-restore` |
| `make v1-pitr TARGET=… SCRATCH_VOLUME=<name>` | Same target, into a separate volume, leaving the live cluster running and untouched |

**What a destructive restore does, in order.** `infra/scripts/platform/pgbackrest-restore.sh` stops the `postgres`
service through the profile's Compose file (`:528-533`), resolves the live volume from Compose metadata (`:535-541`),
and runs `pgbackrest restore` inside the Compose network (`:685-696`). The restore carries `--delta` (`:197-205`):
pgBackRest refuses a non-empty `pg1-path`, and the live data directory is non-empty by definition, so without `--delta`
the command would abort after Postgres is already stopped. A point-in-time run adds
`--type=time --target=<normalised> --target-action=promote` (`:192-195`); the target is validated as ISO-8601 and its
`T` separator and `Z` suffix are rewritten to the `+00` offset pgBackRest's parser accepts (`:171-190`). The script
then proves the result before reporting it: `PG_VERSION` must exist on the volume *before* the server is started
(`:566-571`), because the image's entrypoint runs `initdb` on an empty `PGDATA` and a liveness check alone would report
a fresh cluster as a successful restore; only then does it start Postgres (`:573`) and require
`pg_is_in_recovery()=false` (`:582-595`). `[restore] ok` is printed after that proof (`:702`), and **both destructive
paths leave the cluster running and verified**. They do not stop the application services — an operator drains those
before a restore, and the restore runbook states that sequence.

**Credentials.** `make v1-restore` and `make v1-pitr` export `PGBACKREST_REPO1_CIPHER_PASS`,
`PGBACKREST_REPO1_S3_KEY` and `PGBACKREST_REPO1_S3_KEY_SECRET` from the profile's `0600` `.env`
(`infra/scripts/dev-tool.sh`:607-610). The script writes them to a `0600` file created with `mktemp`, passes it to the
engine with `--env-file`, and removes it on exit (`infra/scripts/platform/pgbackrest-restore.sh`:317-398). It does not
use `-e VAR`: with a rootful engine (`IBEX_PODMAN_SUDO=1` makes the engine `sudo -n podman`) sudo's `env_reset` drops
the exported values, so a name-only `-e` arrives empty and the restore fails after Postgres is already stopped. Before
that destructive step the script starts a probe container the same way and requires every value to arrive intact
(`:422-437,524-526`); a direct invocation with `COMPOSE_FILE` pointing at the v1 profile loads the same three values
from the profile `.env` itself (`:265-295`). No credential belongs on a command line; a process listing would expose it.

**Scheduling.** There is no looping backup service in the profile: a restart-looping scheduler inside Compose is a second
scheduler with its own failure mode and no host-level visibility. Schedule `make v1-backup` from the host instead — a
systemd timer or a cron entry — and monitor `pg_stat_archiver.failed_count` plus the freshness file the script writes
(`ibex-last-backup.txt` and `ibex_backup_metrics.prom`). The textfile collector reads `/var/lib/ibex/backup`; a non-root
operator whose profile has not created that directory gets a loud warning naming the fallback path
(`${XDG_STATE_HOME:-$HOME/.local/state}/ibex/backup`) and must either point the collector there or set
`IBEX_BACKUP_STATE_DIR=/var/lib/ibex/backup` and make it writable. A metric written where the collector does not read is
invisible, so the warning is part of the contract rather than advice.

**Proving PITR without touching live data.** `SCRATCH_VOLUME` restores beside the running cluster and is the recommended
first rehearsal for any target an operator intends to use in an incident: create the volume first
(`podman volume create <name>` or `docker volume create <name>`), then
`make v1-pitr TARGET=… SCRATCH_VOLUME=<name>`. The scratch branch stops nothing and never mounts the live data
directory (`infra/scripts/platform/pgbackrest-restore.sh`:477-510), and it restores without `--delta` because the
volume is empty. The restore runs the profile image as uid 999 so the restored files are readable by the server, and the
printed next step starts the scratch cluster with `-c archive_mode=off` so the restored timeline cannot write into the
live repository (`:501-504`); the scratch copy is left stopped until that command is run. Verify with
`pg_is_in_recovery()`, `pg_last_xact_replay_timestamp()` and a row-level check around the target. A restore into the live
volume must run as uid 999 as well; a root-owned restore leaves a data directory the server cannot read.

**Risk: WAL retention during a repository outage.** With `archive-async=n`, a failed `archive-push` blocks WAL recycling,
so `pg_wal` grows until the repository returns or the disk fills. That is the intended trade — a silent data-loss risk is
worse than a visible disk alarm — but it must be monitored: alert when `pg_stat_archiver.failed_count` increases and on
`pg_wal` size, and treat an object-store outage as a P1 with a bounded time-to-disk-full. Retention is
`repo1-retention-full=2`, so two full backups are kept; a longer window is an operator decision, not a default. On a
fresh install the first archive attempts can fail before `objectstore-init` creates the bucket; those segments stay in
`pg_wal` and are retried, so `archived_count` advances once the stanza is armed. Expect a non-zero `failed_count` at
first start, and alert on it increasing *after* the profile reports up.

**What this does not claim.** This section documents the single-node profile's backup and PITR mechanics. It does not
claim a measured RPO/RTO SLO, an off-site replica, or that the drill has run in a hosted environment; the drill evidence
is local and must be repeated per install.

---

## 4) Source Control → Artifact → Deployment Flow (High-Level)

### 4.1 Release policy versus verified evidence

The following are release-policy requirements, not evidence that the corresponding workflow exists in this baseline:

- `main` should remain deployable.
- A merge may trigger staging only through a verified workflow and artifact record.
- Production promotion requires an approved release and immutable digest.
- IBEX Console staging promotion additionally requires the authenticated browser gate in §1.1.

### 4.2 Artifact immutability

- Build produces immutable artifacts (container images + SBOM).
- Deployments reference images by digest (`sha256:...`), not mutable tags.

### 4.3 GitOps principle

- Desired deployment state is declared in Git.
- ArgoCD reconciles cluster state to Git state.
- For an actually configured GitOps workload, rollback is a Git revert + Argo sync. This document does not establish that such a workflow exists for console.

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

#### Stateless services (proxy / auth / embedder / tokenizer-service / mcp-memory / memory / context / api / console)

Recommended rollout: **blue/green** or **canary** depending on risk. Exact service inventory:
[`services/README.md`](../services/README.md) (planning baseline).

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

- For a deployed service with recorded release evidence, roll back by reverting Git desired state to the prior evidence-backed artifact/image digest and syncing the configured controller.
- For console, the rollback record must identify the prior evidence-backed artifact/digest; if no such artifact is verified, disable or remove the operator origin rather than claiming a rollback to an unverified build.
- Public documentation must remain independently available during an IBEX Console rollback or origin disablement.

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

### 8.2.1 Memory HNSW: load-then-index for large backfills

Steady-state memory writes keep `idx_memories_embedding_hnsw` live (incremental graph updates).
For **large-tenant cold loads / migrations** (tens of thousands of embeddings or more), do **not**
drop the live index on a serving primary without a cutover plan.

**Preferred (offline / maintenance window):**

1. Take the memory write path offline (or divert traffic) for a maintenance window
2. Drop (or defer creating) `ibex_core.idx_memories_embedding_hnsw`
3. Bulk `COPY` / insert rows with embeddings
4. `CREATE INDEX` once with elevated `maintenance_work_mem` (and adequate `/dev/shm` in containers)
5. `ANALYZE ibex_core.memories`
6. Restore traffic

**Online alternative (requires rehearsal):** create a replacement index under a new name with
`CREATE INDEX CONCURRENTLY`, dual-read/validate recall+latency, then swap in a short lock window
and drop the old index — only after the replacement is proven on a staging clone of production
data. Do not leave search without an HNSW index on a live tenant.

Search latency after a correct HNSW build is comparable to incremental; the win is **build
wall-clock**, not query p95. See [ADR-0053](adr/0053-vector-store-abstraction.md) §11 and
`benchmarks/memory/` (`--index-build-mode bulk|incremental`).

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
7. `services/console` (canonical authenticated operator application; deploy only after its artifact, runtime owner, and promotion evidence are verified)

The dashboard compatibility shell was retired by ADR-0090. `services/console` is the only operator deployment.

**Important:** Many services can start without their deps (but not be ready).
Readiness probes control routing. Do not “hard fail” startup unless configuration is missing.

---

## 14) Operational Playbooks (Minimum)

### 14.1 Rollback playbook (stateless)

1. Identify the prior evidence-backed artifact/image digest for the affected service.
2. If console has no verified prior artifact/digest, disable or remove the operator origin and keep public documentation independently available; do not roll back to an unverified build.
3. Update Git desired state (Helm values or manifest) only when the prior artifact/digest is recorded.
4. ArgoCD sync, if a configured GitOps workload exists.
5. Confirm:
   - error rate back to baseline
   - latency back to baseline
   - fallbacks return to baseline
6. Write incident notes with:
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
  - authenticated IBEX Console browser promotion suite; do not substitute public-docs or compatibility-shell load

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
7. IBEX Console: run the authenticated staging browser promotion suite; do not substitute a public-docs or compatibility-shell load check.

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
