# v1-single-node start record — 2026-11-07

**Status:** Local acceptance record for the `v1-single-node` profile selected by
[ADR-0097](../adr/0097-v1-supported-profile.md). It records one start on one host in the self-contained
`staging` + `mock` posture. It is **not** a production, hosted, HA, multi-user, or measured-SLO acceptance, and it does
not close P0-22 on its own.

## Environment

- Linux host with 14 GiB RAM; rootless Podman 5.7.0. The Docker CLI was present but its daemon was not running;
  `infra/scripts/dev-tool.sh` now requires a reachable daemon before selecting Docker, so the operator entry point
  selected Podman.
- Edge host port `8443` → Caddy `8443`. Posture `IBEX_ENV=staging`, `IBEX_LLM_MODE=mock`.
- Pins: Caddy `2.11.9-alpine@sha256:0bbb055b…`; TEI `cpu-1.9.4@sha256:2538ea1c…` serving `BAAI/bge-m3` revision
  `5617a9f61b028005a4858fdac845db406aefb181`; pgvector `0.8.6-pg16@sha256:ccc6e83d…`; Redis
  `7.4.2@sha256:fbdbaea4…`. All application images were built from their service Dockerfiles; `migrate` from
  `infra/migrations/Dockerfile`.

## Start

`make v1-secrets` generated `infra/compose/v1-single-node/.env` (0600), `secrets/` (0700; file copies 0444), and the
per-install CA plus auth/edge leaves.

`make v1-up` exited 0 and printed `v1-single-node is up: https://localhost:8443`.

- `migrate` exited 0 (`migrate up: ok`).
- `bootstrap` exited 0 and created the organization, owner user, agent, allow-all model policy, the admin PAT
  (`Admin | SecretUse | OperatorMetadataRead`), and the scoped memory `service_token` (`MemoryRead | MemoryWrite`).
- All twelve long-running services reported `healthy`: auth, proxy, api, memory, context, embedder, worker, console,
  edge, postgres, redis, tei.
- `ss -ltn` showed only the edge HTTPS listener `*:8443`; no datastore, AuthService, context, memory, or worker port
  was published.

## Journey

| Check | Result |
|---|---|
| `GET /_edge/health` | `200 ok` |
| `GET /health`, `/ready`, `/metrics` | `404` |
| `GET /v1/internal/auth-probe`, `/v1/internal%2Fauth-probe` | `404` |
| `POST /v1/operator/session/login` with the bootstrap PAT | `200`, Auth-owned session, cookies set |
| `GET /v1/operator/overview` with the session cookie | `200`, org `ibex`, one active user and agent |
| `POST /v1/chat/completions` (PAT, `X-IBEX-Agent-ID`, `Idempotency-Key`) | `200`, one mock completion |
| Context assembly (proxy fail-open count after the 2 s budget) | `0`; context log shows hot-cache and semantic-search calls `200` |
| Memory write (benign content) | `201`, `active`, embedded |
| Memory search (same agent, `min_similarity=0`) | `200`, one active hit |
| Memory write flagged as PII | `202`, `quarantined`, no embedding (by design) |
| Console SSR `/` | `200`, title `Overview · IBEX Console` (live data through the BFF → edge → API loopback hop) |
| Unauthenticated chat | `401 MISSING_TOKEN` |
| Plaintext gRPC to AuthService from the API netns | `UNAVAILABLE` (TLS required) |
| Host ports `5432/6379/9091/8080/8010/8005/8007/9092` | refused |

The `make v1-ps` `PORTS` column shows `8443` on the co-located API, proxy, console, and context because they share the
edge network namespace. The host listener check (`ss`) is the authoritative surface: one published port.

## Defects found and fixed during the start

1. **API Redis alias.** `services/api/app/config.py` used the `IBEX_API_` prefix for `redis_url` while the compose and
   `ENVIRONMENT_VARIABLES.md` use `REDIS_URL`. Added `AliasChoices("REDIS_URL", "IBEX_API_REDIS_URL")` and two tests.
2. **Operator login 401.** The API sent both the PAT and the service token to `IssueOperatorSession`; the auth
   interceptor's service-token path won and left the caller context unset. Login now sends the PAT only; refresh keeps
   the service token. The session-refresh tests were updated.
3. **Healthcheck quoting.** The console and context `CMD` healthchecks were split by the runtime at the first space or
   semicolon. Both are quoted `CMD-SHELL` scripts now and reach healthy.
4. **Worker image shebangs.** The runtime copied the venv from `/app/services/worker/.venv` to `/app/.venv`, leaving the
   `celery` console-script shebang pointing at the build path. The runtime keeps the venv at its absolute path; the
   worker and `worker-beat` commands now start.
5. **Policy-snapshot verifier.** Staging/production refuse to mount protected proxy routes without a verifier. The
   secret generator now writes `policy_public_keys.json` (key id `v1`, epoch `1`) and the proxy mounts it.
6. **Memory service token.** The bootstrap service did not receive `IBEX_MEMORY_API_TOKEN`. It does now, and the
   bootstrap reconciles the scoped row on later runs without reactivating a revoked token; the real-Postgres
   integration test covers creation, rotation, and revocation refusal.
7. **CPU embedding budgets and TEI first start.** The 45 ms context budgets and a 10-minute TEI health window cannot
   accommodate CPU query embedding and a 2.3 GB first download. The profile now uses a 2 s proxy/context budget, a
   two-hour TEI window, `HF_HUB_DISABLE_XET=1` (the Xet path was ~4× slower here), and a 2048-token/16-concurrent
   batch. The host needed roughly 10 GB free during the one-time TEI warmup; the reference sizing is a 16 GB host.

## Review hardening (after the PR review)

- The tracked profile template moved to `infra/compose/v1-single-node/.env.example` so the repository layout guard
  accepts it.
- The admin PAT is written through a host bind mount (`infra/compose/v1-single-node/bootstrap/`, directory `0700`,
  file `0600`) instead of a container tmpfs, so it survives the one-shot's exit; `make v1-bootstrap-pat` reads the host
  file rather than `cp`-ing from a container (which streams a tar archive and depends on the same rootful/rootless
  store). The write is atomic (temp file plus rename), so a pre-existing permissive file is replaced rather than
  reused, and a symlink at the destination is replaced rather than followed. `IBEX_BOOTSTRAP_PAT_FILE` is required, so
  the command can no longer print the credential to stdout.
- `make v1-up` rebuilds the images, waits for every required service through the runtime's health state (portable
  across Docker Compose and podman-compose), and performs a full stop/start when the certificate fingerprint changes
  under `IBEX_V1_CERTS_DIR` (Compose cannot replace the edge while the co-located containers exist). A failed teardown
  aborts the recipe instead of clearing the marker. `make v1-migrate` rebuilds the migration image. `make v1-down`
  retries once after a rootless-netns cleanup error. `infra/scripts/lib/dotenv.py` is the single reader for Compose
  `.env` semantics in both scripts (quotes, `KEY = value`, inline comments, last assignment wins).
- The API binds loopback inside the edge namespace; organization deletion is wired to the worker broker and the
  `postgres,redis` store set; the worker healthcheck also pings the Celery consumer.
- The bootstrap implementation moved to `services/auth/internal/bootstrap`; the token reconcile filters by `org_id`,
  binds only an **active** owner and agent, refuses to write an unbound token, refreshes the subject, clears an
  expired row, serializes per organization, and revokes duplicate managed rows. Tests cover cross-tenant isolation,
  PAT re-verification, duplicate revocation, the missing-subject refusals, the real `Run` entrypoint (including its
  failure paths), and every SQL error return through a stdlib fault-injection driver.
- The operator guide verifies the edge certificate with `--cacert` and the printed edge URL, rotates certificates under
  `certs/`, checks out the target release before rebuilding, drains pending extraction work before the snapshot, and
  documents the Redis reconciliation step for rollback.

## Limitations and residuals

- This record is `staging` + `mock` only. The supported production posture is `production` + `live` with an
  operator-supplied provider key; it is not recorded here.
- P0-22's audit criterion names a start on `IBEX_ENV=production` that serves an authenticated chat request. The edge
  terminator, the transport fixes, and an authenticated staging start now exist; the production start remains open.
- The worker's extraction path has no live LLM in mock mode; extraction quality is not part of this claim.
- One host and one tenant. Cross-tenant acceptance, recovery drills, and measured p99 SLOs remain open.
- TEI's first fetch is network-bound; the `tei-cache` volume persists it. CPU TEI with a 2048-token batch may truncate
  long memories.
- A PII-flagged memory is quarantined before embedding; that is the intended content-trust behavior, not a failure.

## Evidence commands

```bash
make v1-secrets
make v1-up
make v1-ps
curl -fsSk https://localhost:8443/_edge/health
curl -sk -o /dev/null -w '%{http_code}\n' https://localhost:8443/v1/internal/auth-probe
ss -ltn
# Confirm only the edge HTTPS port is published. No datastore, AuthService,
# context, memory, or worker port may appear.
```

The repository gates for this change were run locally: Go auth/proxy suites, the API suite (901 passed), console
(181), context (420, 99.41% coverage), the bootstrap real-Postgres integration test, the site
build/check/lint/typecheck, Markdown lint, and `agent-docs-check.sh fast`.

## Verification notes

- An independent verifier reproduced every claim in this record against the running stack and the working tree.
- A fresh `pnpm site:build` passed (2m39s, 361 routes), and `site:typecheck`, `site:lint`, and `site:check` passed. One
  earlier stored build log ended in a Nitro prerender timeout; it is treated as environment-transient and is not the
  basis of the claim.
- Under the coverage run, one pre-existing timing-sensitive test
  (`test_packer_latency.py::test_packer_dp_latency_p99_under_5ms_at_n70`) measured 5.118 ms against a 5.0 ms budget; it
  passes when run alone, and the context coverage number reproduced exactly at 99.41%. It is not a regression in this
  change.
- After a host restart, one operator-overview request returned `503 SERVICE_DEGRADED auth unavailable` while the API
  reconnected to AuthService; the retry returned 200. This is startup ordering, not a data-path failure.
- The heavy local scanners were run with the profile stopped (the 14 GB host cannot hold both): CodeScene passed with
  zero findings across all 21 changed eligible files; SonarQube reported zero issues on every changed production and
  test file after one duplicated banner literal was replaced with a constant; Codacy's only changed-file findings (a
  Dockerfile consecutive-`RUN` warning and a test PEM fixture matched by the private-key detector) were fixed and the
  two files re-analyzed clean. Codacy's remaining findings are in files this change does not touch and are not
  introduced by it. The profile was restarted afterwards.
- After the scanner-driven refactors, the auth and API images were rebuilt and the profile was restarted
  (`make v1-up`, exit 0). The bootstrap reconciled the existing organization and memory token without issuing a new
  PAT. All twelve services were healthy; login, overview, and chat returned 200; context assembly reported no
  fail-open; memory search returned 200; the edge negatives and the single host listener were unchanged.
