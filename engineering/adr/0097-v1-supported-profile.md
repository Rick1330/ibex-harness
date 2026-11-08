---
title: "ADR-0097: Select the v1.0 supported profile (single-node self-hosted Compose)"
description: "Architecture decision record 0097: one supported deployment profile for v1.0, its component and transport contract, its dependency matrix, explicit exclusions, and the evidence each later gate inherits."
adrId: "0097"
status: "Accepted"
date: "2026-11-06"
authors: "Elshaday Mengesha (@Rick1330)"
---

::decision-banner{status="Accepted" date="2026-11-06" id="0097"}
::

# ADR-0097: Select the v1.0 supported profile (single-node self-hosted Compose)

- **Status:** Accepted
- **Date:** 2026-11-06
- **Authors:** Elshaday Mengesha (@Rick1330)
- **Gates:** G8 (operations/recovery), and every runtime gate that needs a named environment to score against
- **Depends on:** [ADR-0096](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0096-context-grpc-caller-authentication.md)
  (context caller authentication and the loopback-only plaintext boundary),
  [ADR-0089](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0089-product-shape-and-console-scope.md),
  [ADR-0090](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0090-retire-dashboard-compatibility-shell.md)
- **Accepted by:** the 2026-11-06 G0 review record
  ([`28-g0-review-record-2026-11-06.md`](../architecture-v2/28-g0-review-record-2026-11-06.md)), decision D5

## Context

`engineering/RELEASING.md` requires explicit production-readiness and compatibility sign-off before `v1.0.0`, and the
ledger's claim rule requires a deployment profile before any runtime claim can rise above `provisional`
(`00-status-and-evidence.md:7-13`). No profile has ever been selected: the contract registry still records "Profile not
selected" on five rows (`03-contract-registry.md:129,139,149,169,179`), and the readiness audit recorded the missing
decision as D5, with 22 P0 rows (21 open) scored against an assumed target
(`27-v1-readiness-audit.md` §6, §7).

Two candidates were realistic: Kubernetes with HA, and a single-node self-hosted Compose stack. The Kubernetes path is
not deployable today — `infra/helm/ibex-harness/values.yaml` carries sentinel digests for every image, the migrate job is
disabled, and no install, upgrade, or restore has been executed. Choosing it would make 1.0 a claim about infrastructure
that does not exist. The Compose path is closer, but its gaps are equally real: `services/context` has no image and
refuses non-loopback binds, the Console has no image, and no profile starts the documented critical path.

The audit's domain reviews also found that the present transport postures contradict each other. This ADR cannot select
a profile without resolving them, because a profile is precisely a statement about which processes talk to which, over
what transport, with what authority.

## Decision

**1. The v1.0 supported profile is single-node self-hosted Docker Compose, named `v1-single-node`.** It is the only
profile a 1.0 claim may cite, and every acceptance artifact must name it. A development host-run stack and a Kubernetes
install are not this profile and cannot supply its evidence.

**2. Component set.** One Compose project, one `.env`, one operator entry point.

| Component | Artifact at `b400070f` | In `v1-single-node` |
|---|---|---|
| AuthService (gRPC) | Dockerfile + `push-auth` job | required |
| Proxy | Dockerfile + `push-proxy` job | required |
| Management API | Dockerfile + `push-api` job | required |
| Memory | Dockerfile + `push-memory` job | required |
| Context assembly (gRPC) | **no Dockerfile, no publish job** | required, co-located with the proxy (§4) |
| Embedder | Dockerfile + `push-embedder` job | required, pointed at TEI (§6) |
| Worker | Dockerfile + `push-worker` job | required |
| Console (Nuxt + Nitro BFF) | **no Dockerfile, no publish job** | required for the operator product |
| Edge TLS terminator | **absent** | required (§5) |
| Migrations | `infra/migrations/Dockerfile` exists, runs as a one-shot service, **no publish job** | required, one-shot gate (§7) |
| PostgreSQL + pgvector | `pgvector/pgvector:0.8.6-pg16@sha256:ccc6e83d…` in the bundle and CI | required |
| Redis | `redis/redis-stack:7.4.0-v1` in dev/test; `redis:7.4.2` with a sentinel digest in Helm | required, plain Redis (§8) |
| MCP memory | Dockerfile + `push-mcp-memory` job | optional, default off |
| MCP operator | Dockerfile, **no publish job** | optional, default off, and not claimable until published |
| Relay | no Dockerfile | optional, default off (`IBEX_RELAY_ENABLED=false`) |
| ClickHouse | pinned `24.8.14.39` in every compose file | optional projection |
| MinIO / S3 | Chainguard digest pin in dev compose and the host overlay | optional archive |
| Reranker (TEI cross-encoder) | **no pin, no artifact** | optional (ADR-0093), default off |
| OTel collector / Tempo / Grafana / Loki | digest-pinned observability compose | optional |

The operator entry point is `make v1-up`, `make v1-down` and `make v1-migrate`. **None of these targets exists yet**
(`Makefile` has `compose-dev-up`, `compose-test-up`, `stack-init` and `readiness`); they are W2 acceptance items, and no
document claims them before they run. The profile also ships a tracked
`infra/compose/v1-single-node/.env.example` copied to `infra/compose/v1-single-node/.env` (mode `0600`). That path is
separate from the repository's development `.env`; the root `.env.example` the quickstart tells readers to copy does
not exist.
on a clean clone.

**3. "Required" means startup-gating; "optional" means visibly degraded.** The profile does not start if a required
dependency is unavailable: the one-shot migration service must exit zero, and every required service must report
`/ready`. An absent optional component must appear as a named degraded check on `/ready` and in the Console platform
surface — never as silence and never as a hard failure.

**4. Transport contract.** Plaintext is permitted only on loopback inside a single network namespace; every listener
reachable by more than one peer carries TLS.

- **Context ↔ proxy: co-located, loopback, plaintext.** The context container runs with
  `network_mode: "service:proxy"`, binds `127.0.0.1` only, and the proxy dials the loopback literal. This preserves
  ADR-0096's boundary instead of weakening it: `services/context/app/server.py` already refuses any non-loopback bind,
  and `services/proxy/internal/config/config_validate.go` already refuses a non-literal target.
- **The environment gate is replaced by an explicit co-location opt-in.** Today the proxy also refuses
  `IBEX_CONTEXT_ENABLED=true` for any `IBEX_ENV` other than `development`, because the context server cannot serve TLS
  and a TLS dial would fail open to directive-only context. That gate is a proxy for the real property (loopback
  co-location), and in `v1-single-node` it would make the required component unusable. It is replaced by a fail-closed
  pair: the target must be a loopback literal (existing rule) **and** the profile must set an explicit
  `IBEX_CONTEXT_COLOCATED=true`. Without that opt-in, non-development environments still refuse to enable context. The
  change is security-relevant and lands with the negative tests named under **Evidence required**.
- **AuthService gRPC: TLS with a per-install CA.** Auth serves multiple peers, so it cannot be co-located. Today the
  server serves plaintext (`services/auth/cmd/auth/main.go`, `newAuthGRPCServer` registers no transport credentials),
  the Go proxy dials TLS for every environment except `development`/empty
  (`services/proxy/internal/bootstrap`, `authTransportCredentials`), and the Python API dials
  `grpc.aio.insecure_channel` behind `assert_trusted_insecure_auth_target` (`services/api/app/auth/session_refresh.py`,
  `packages/authclient/src/authclient/target.py`). Diagnosed per hop: **proxy → auth always fails outside `development`**
  (TLS client against a plaintext server), and that is the hop every chat request needs; **API → auth works**, because
  both sides are plaintext over a Compose short name, but with no transport security. The profile requires: TLS server
  credentials on AuthService, a CA file plumbed to the Go and Python clients, and one negative test proving an
  unauthenticated client is rejected. The auth port is never published to the host.
- **Edge TLS terminator: one origin, explicit path ownership.** The Console BFF refuses to send a session cookie to a
  non-HTTPS API origin (`services/console/server/utils/operator/http.ts`, `fetchOperatorJson`), and the browser session
  cookie requires a secure origin. The profile therefore ships a terminator on the single published HTTPS port, and it
  must route by exact path prefix, not by a blanket `/v1`: **the proxy and the API both own `/v1` routes.**

  | Path | Upstream | Why |
  |---|---|---|
  | `/v1/chat/completions` | proxy | `router_protected.go:182` |
  | `/v1/responses` | proxy | `router_protected.go:198` |
  | `/v1/sessions/{session_id}/terminate` | proxy | `router_protected.go:102` |
  | `/v1/orgs/{org_id}/auth-probe` | proxy | `router_protected.go:134` |
  | `/v1/internal/auth-probe` | proxy | `router_protected.go:131`; internal-only, never published |
  | `/v1/operator/*` | API | the Console BFF's upstream paths (`services/console/server/utils/operator/http.ts`) |
  | `/v1/organizations/*`, `/v1/tokens`, `/v1/users`, `/v1/agents`, `/v1/tenant/*` | API | `services/api/app/routers/*` |
  | everything else | Console | Nuxt SSR routes; `/health`, `/ready` and `/metrics` are not published at the edge |

  The BFF's `API_ORIGIN` is the edge URL, not the API container, because the cookie rule keys on that origin. Cookie
  `Domain` is never widened to a parent domain, and the BFF never accepts an upstream redirect.
- **Internal HTTP APIs** carry the existing shared bearer tokens (`IBEX_MEMORY_API_TOKEN`, the worker enqueue token,
  the embedding token) over the Compose bridge, with the port unpublished. This is a host-local bridge, not a public
  interface; it is documented as a limitation, not as a security boundary.

> **Amendment 2026-11-07 — edge-anchored application plane.** Implementing W2.4 showed that the original
> `service:proxy` anchor would leave the edge → proxy/API/console hops carrying browser credentials (PAT, session
> cookie) as plaintext on the shared Compose bridge. That contradicts this section's rule: plaintext is permitted only
> on loopback inside a single network namespace. The profile therefore anchors the application plane on the edge:
> `proxy`, `api`, `console`, and `context` all use `network_mode: "service:edge"`, and the edge is the only service with
> a published port. The property above is preserved and strengthened: context still binds `127.0.0.1` only, the proxy
> still dials the loopback literal, and the browser-credential hops are now loopback as well. `IBEX_EDGE_PORT` is the
> host-side mapping; inside the namespace the edge listens on `8443`, so the console BFF dials
> `https://localhost:8443` while the browser uses `https://localhost:${IBEX_EDGE_PORT}`. Operational consequence:
> replacing the edge requires a full profile restart (`make v1-down` then `make v1-up`); Compose cannot recreate the
> edge while the co-located proxy, API, console, and context containers exist, and it does not restart them
> automatically. `make v1-up` performs the restart itself when the certificate fingerprint changes. No other decision
> changes.

**5. Only two ports are published:** the edge HTTPS port, and nothing else. Datastores, AuthService, context, memory,
worker and the MCP services are reachable only inside the Compose network.

**6. Semantic memory requires a real embedding backend.** The memory schema stores `vector(1024)` and enforces
`embedding_dim = 1024` (`infra/migrations/postgres/000017_memory_schema_v2_expand.up.sql`), which is `BAAI/bge-m3`
geometry. The bundle satisfies that constraint with the stub: it sets `IBEX_EMBEDDING_PROFILE=cpu` **and**
`IBEX_EMBEDDING_DIM=1024`, and the stub emits deterministic 1024-dimension vectors. Writes therefore succeed and rows are
schema-valid — but the geometry carries no meaning, so retrieval quality is arbitrary, which the bundle's own `limits`
already records. `v1-single-node` therefore runs TEI serving `BAAI/bge-m3` at 1024 dimensions for any semantic-retrieval
claim, with a pinned image tag and model revision; the `cpu` profile is a test fixture that no 1.0 claim may cite. TEI
has no image pin today (`infra/reference/tei-embeddings.compose.yaml` is reference-only); pinning it is an acceptance
item.

**7. Migrations run as a one-shot service before any application container.** The image is built from
`infra/migrations/Dockerfile`, runs `migrate up`, and gates application startup on `service_completed_successfully`. The
pattern is already implemented, not invented: `infra/compose/bundles/memory-context.yml` runs the one-shot `migrate`
service, `seed` and `auth` gate on it with `service_completed_successfully`, and `memory` gates on `seed` completing plus
`auth` and `embedder` health. The gate is not uniform — `embedder` has no `depends_on` at all — so the profile applies it
consistently to every required service, including the Console, proxy and context it adds. A failed migration stops the
stack; there is no partial start. ClickHouse migrations run only when ClickHouse is enabled.

**8. Data-plane pins, resolved once.**

| Dependency | Supported pin | Why |
|---|---|---|
| PostgreSQL + pgvector | `pgvector/pgvector:0.8.6-pg16`, digest `sha256:ccc6e83d…` | Bundle and CI already pin this digest; the mutable `:pg16` tag in dev compose and site docs is not a supported artifact, and the sandbox run recorded on pgvector 0.8.7 is not a support claim |
| Redis | `redis:7.4.2` version-pinned; the digest must still be captured (the Helm digest is a sentinel) | No Redis Stack module command exists in code: rate limiting is Lua `INCR`+`EXPIRE`, extraction buffers use Lua CAS, revocation uses streams. `redis/redis-stack:7.4.0-v1` stays a dev convenience, not the supported artifact |
| ClickHouse | `clickhouse/clickhouse-server:24.8.14.39` | Every compose file pins it; `TECH_STACK.md` saying 23.x is documentation drift, corrected in the same change |
| MinIO | Chainguard digest already pinned in `infra/compose/dev/docker-compose.yml` and the host overlay; not in the bundle | Archive only; optional |

**9. Upgrade and rollback are stop-the-stack operations.** Upgrade: stop the stack, take a database snapshot, run the
one-shot migration service, start the new images by digest. Rollback: restore the snapshot and start the previous
digests. Because migrations are forward-only, "start the previous digest against the migrated schema" is not a
supported rollback and the release note must not imply it is.

**10. Exclusions, stated as a list.** These are out of 1.0 scope, in the words a release note may reuse:

- Kubernetes, Helm and any HA topology; no rolling upgrade; a restart is an outage.
- Hosted or measured SLOs; no p99 claim, and no benchmark result is an SLO.
- Response-bound evidence acknowledgement. Evidence is acknowledged post-response, on the durable outbox commit.
- The run envelope as a runtime artifact: no persistence, replay, or approval consumption exists in the repository today, so 1.0 cannot claim it.
- `DecisionService`, MCP writes (MCP memory is read-only and default-off; MCP operator is not published).
- The platform-tier Console surfaces (ADR-0089). Only the `core` surfaces are in scope.
- ClickHouse and MinIO/S3 projections, the reranker, and the observability stack: optional, default off.
- Multi-user authentication. `PrincipalContext` is unsigned and confined to a loopback namespace, so per-user
  authentication and any non-loopback deployment are unsupported.

**11. Readiness contract, stated honestly for today and for the gate.** Today memory's `/ready` reports bootstrap state
only — it surfaces an initialisation error and nothing per request (`services/memory/app/probes.py`); the API does check
PostgreSQL and AuthService per request (`services/api/app/probes.py`); the proxy registers PostgreSQL, the tokenizer and
a self-hosted LLM as **advisory** checks that do not gate readiness (`services/proxy/internal/bootstrap/wire.go`); the
worker's enqueue HTTP app does expose `/ready` (enqueue token, PostgreSQL ledger, Redis) but its Celery process is covered
only by a container `HEALTHCHECK` (`services/worker/app/enqueue_http.py`, `services/worker/scripts/healthcheck.sh`); and
the Console exposes no `/ready`, while context registers no `grpc_health_v1` service.

The 1.0 gate is: every required service exposes `/ready` probing each dependency it declares in §8, optional dependencies
appear as named degraded checks, and the migration gate is visible. Until that is true, no 1.0 claim may cite readiness.

## Consequences

**Positive.** Every remaining gate has a named environment, so the audit's W2–W9 exit criteria become scoreable rather
than rhetorical. The transport contract turns three contradictory postures into one decision, and the embedding decision
turns "semantic search works" from an assumption into a pinned artifact. Explicit exclusions convert silent gaps into
sentences a release note can carry.

**Negative.** 1.0 will be a single-node release: no HA claim, no rolling upgrade, and a restart is an outage. The profile
cannot be started today — context, console, edge termination, the migration image job and the TEI pin all have to be
built, and AuthService needs TLS before any non-development start succeeds. Selecting the profile closes none of the
audit's P0s; it makes them measurable. The evidence required at the end of this record is work, not a formality.

**Neutral.** This decision does not promote a ledger row, does not accept a contract shape, and does not resolve D1 (no
independent reviewer), D4 (relay `required_evidence` gate) or D6 (unsigned `PrincipalContext`). Those stay open and are
recorded as open in the G0 review record. The registry's "Profile not selected" column changes to `v1-single-node` when
the profile actually starts, not on merge of this record.

## Alternatives considered

1. **Kubernetes with HA.** Rejected for 1.0: the chart is lint scaffolding with sentinel digests, the migrate job is
   disabled, datastore templates are missing, and no install, upgrade, or restore has run. Choosing it would make 1.0 a
   claim about infrastructure that does not exist.
2. **Keep the host-run development stack as the profile.** Rejected: it is not a deployment, has no images, no upgrade
   path, no TLS, and `services/context` cannot bind a network interface.
3. **One all-in-one container.** Rejected: it hides the service boundaries the architecture depends on and makes
   per-service readiness and failure isolation impossible.
4. **Exclude context assembly from 1.0 and run directive-only.** Rejected: context assembly is the product. It is also
   avoidable — co-location preserves ADR-0096's loopback boundary without weakening it.
5. **Defer the decision until the artifacts exist.** Rejected: without a profile every gate is scored against an
   undefined environment, which is the condition the audit found.

## Evidence required

- `make v1-up` starts the profile on a clean host, in the documented order, with the migration gate green and every
  required `/ready` passing; `make v1-down` leaves no container and no orphaned volume.
- A recorded critical journey in `v1-single-node`: authenticated chat through the proxy with context assembly, a memory
  write, a memory search returning the written memory, and the Console read path through the edge terminator.
- The negative transport tests: an unauthenticated AuthService client is rejected; a non-loopback context target is
  refused; the co-location opt-in is required outside `development`; no datastore or gRPC port answers from the host.
- Every required image is published, digest-pinned, signed, and present in `release-manifest.json`; the bundle smoke runs
  on the release commit.
- The dependency matrix and the exclusion list appear verbatim in `engineering/DEPLOYMENT.md` and the public deployment
  docs, and the exclusions appear in the release note.
- A `v0.1.9` → 1.0 upgrade rehearsal from a real snapshot and a rollback rehearsal that restores it.

## References

`engineering/architecture-v2/27-v1-readiness-audit.md` §6–§7; `28-g0-review-record-2026-11-06.md`;
`26-g0-review-packet.md` (D5); `engineering/RELEASING.md`; `infra/compose/bundles/memory-context.yml`;
`infra/compose/dev/docker-compose.yml`; `infra/migrations/Dockerfile`; `services/*/Dockerfile`;
`services/context/app/server.py`; `services/proxy/internal/config/config_validate.go`;
`services/auth/cmd/auth/main.go`; `services/console/server/utils/operator/http.ts`;
`infra/migrations/postgres/000017_memory_schema_v2_expand.up.sql`; `services/embedder/app/profiles.py`;
`infra/reference/tei-embeddings.compose.yaml`.
