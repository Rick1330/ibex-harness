# Production-Readiness Infrastructure Audit and No-Deploy Workplan

**Status:** `proposed` — audit and sequencing input; not G0 acceptance, a deployment profile, or production-readiness certification.

**Audit checkout:** `chore/IBEX-939-g0-gap-audit-docs` at `9fcf725740e027b52f3a30e6b435b12a31000650` (2026-10-06).

**Scope direction:** On 2026-10-06, the task owner selected provider-neutral Kubernetes/Helm application preparation with external data-plane interfaces; provider-specific IaC is deferred, deployment is prohibited, and no HA/support claim is made until evidence exists. Development Compose remains local-only. This is a preparation direction, not a supported production profile or G0 acceptance.

**Milestone:** [4.P.5 — Production Platform, Recovery & Supply Chain](../../content/roadmap/phase-4-multi-provider/milestones/4.p.5-production-platform-recovery-supply-chain.mdx), still `in-progress` / partial.

## 1. Executive assessment

IBEX has a meaningful production-oriented foundation: seven application Dockerfiles, multi-architecture image publication and signing for those seven services, a Kubernetes/Helm application chart, digest guards, migration code, security policy, monitoring configuration, backup tooling, runbooks, and a local restore-drill harness. These assets are **not** equivalent to an accepted, deployable, recoverable production platform.

The production Helm overlay intentionally contains sentinel image digests and says not to deploy it. The chart is application-only; external data planes and Secrets are prerequisites, migration execution is not wired into a verified release path, and the production promotion path is not evidenced. The historical recovery drill is local and explicitly did not measure PostgreSQL RPO, ClickHouse recovery, or object-store recovery. Kyverno admission was not applied in that drill. No production cluster, cloud account, real credentials, or live release was used in this audit.

**Conclusion:** The owner-selected preparation direction is provider-neutral Kubernetes/Helm application packaging with external data-plane interfaces; provider-specific IaC and deployment are deferred, and no HA/support claim is accepted before evidence. G0 remains `UNKNOWN / NOT ACCEPTED`. Until the formal G0 and relevant later gates are satisfied, permitted work is limited to inventory, documentation, owner-decision preparation, review evidence, and test-matrix preparation. Do not turn this plan into an implementation or support claim by implication.

## 2. Scope and no-deploy boundary

Development Compose remains the choice for the **local integration profile**. The task owner selected the following production-preparation direction: provider-neutral Kubernetes/Helm application packaging with external data-plane interfaces, provider-specific IaC deferred, no deployment, and no HA/support claim until evidence. This selection does not specify actual external services, select a provider/region or supported topology, supply missing domain-owner approvals, accept G0, or authorize a deployment.

For this work, do **not**:

- Run `helm install`, `helm upgrade`, `kubectl apply`, Terraform/OpenTofu apply, or any other resource-provisioning action.
- Create cloud resources, production/staging namespaces, external Secrets, DNS records, certificates, or credentials.
- Publish or promote images, trigger Docker/release workflows, or trigger Cloudflare/web/operator deployments.
- Replace the production sentinel digests with guessed or locally generated digests.
- Claim a production, HA, recovery, security-admission, or support guarantee from source files or historical local evidence.

The existing user direction authorizes preparation and repository changes under the task owner’s authority; it does not establish approvals from unassigned Security, Privacy/Legal, Finance, Platform/SRE, or independent review owners. The exact supported topology, provider/region, data-plane ownership, and production support boundary remain open decisions.

## 3. Verified production-oriented foundation

The following is a source-level inventory, not a statement that production behavior was executed or accepted:

- **Application packaging:** `infra/helm/ibex-harness` templates seven workloads: proxy, auth, API, worker, memory, embedder, and MCP memory. The 4.P.5 milestone separately requires the canonical Console workload before operator-runtime promotion; the chart README labels the checked-in chart and values as render/lint scaffolding.
- **Artifacts:** Seven service images have configured multi-stage builds, non-root runtime users, multi-architecture publication, pre-publish Trivy scans, provenance attestations, and keyless Cosign signing. The migration Dockerfile is outside the identified build/scan/publish/attestation matrix. All-image post-push digest verification is incomplete.
- **Chart checks:** Helm lint/template/profile regression and digest/sentinel guard scripts exist. They are not evidence of a live Kubernetes API, admission policy, ingress, HPA/PDB behavior, or a release promotion. The audit environment lacked Helm, so the checks were not rerun.
- **Secrets and data plane:** The application chart uses external Secret references and does not provision PostgreSQL/pgvector, Redis, ClickHouse, MinIO/S3, queues, or a secret manager. The production values file contains sentinel digests and a conceptual S3 endpoint; those values do not make the overlay deployable.
- **Runtime security:** Application templates include several useful controls (non-root, no privilege escalation, read-only root filesystem, disabled service-account token automount, probes, and resource settings). The chart does not yet establish a complete network/RBAC/Pod Security boundary; the migration Job has a separate hardening gap.
- **Recovery and operations:** PostgreSQL/ClickHouse migrations, pgBackRest scripts, local monitoring, runbooks, and a restore-drill harness exist. The committed drill is not production evidence: PostgreSQL RPO was unmeasured/failed, ClickHouse and MinIO timings are null, the run used a local fallback rather than pgBackRest PITR, and Kyverno was not applied.

Primary source records: [application chart README](../../../infra/helm/ibex-harness/README.md), [production values](../../../infra/helm/ibex-harness/values-prod.yaml), [infrastructure inventory](../../../infra/README.md), [4.P.5 milestone](../../content/roadmap/phase-4-multi-provider/milestones/4.p.5-production-platform-recovery-supply-chain.mdx), [backup boundary](../../../infra/backup/README.md), and [monitoring boundary](../../../infra/monitoring/README.md).

## 4. Production blockers from the five-area audit

### 4.1 Governance and supported profile

G0 acceptance is absent. There is no accepted production profile, provider/account/region, tenancy or residency boundary, cost envelope, operational owner/on-call path, or exact dependency/image/config evidence bundle. The repository explicitly distinguishes Development Compose, single-node self-hosted, and HA production; acceptance in one profile does not transfer to another.

**Required before implementation-ready claims:** complete the owner worksheet in [21-g0-owner-decision-recommendations.md](21-g0-owner-decision-recommendations.md), name accountable domain/review/evidence owners, and record the accepted commit, profile, dependencies, limitations, date, and review/expiry date in [00-status-and-evidence.md](00-status-and-evidence.md).

### 4.2 Chart completeness and configuration contract

The production overlay is deliberately non-deployable: each image entry, including migration, is a repeated-character sentinel. The chart has no data-plane templates; production ingress is disabled unless explicitly configured; Secret creation/rotation is external; the migration Job is disabled by inherited defaults; and the chart does not contain the canonical Console workload required by the 4.P.5 exit criteria.

Audits also found incomplete or absent service environment/Secret wiring for documented PostgreSQL, Redis, ClickHouse, S3/object, provider, Auth, and OTLP dependencies. API/Auth, worker, memory, MCP-memory, and proxy must each be reconciled against their service configuration contracts before a rendered release can be considered complete.

### 4.3 Artifact lifecycle and migration image

The migration image is not included in the existing service-image build, scan, publication, post-push verification, or provenance-signing flow. CI scans pre-publish images but the identified post-push digest scan covers only the worker. No release evidence bundle was found that binds the source commit, every exact image digest, chart version, merged-values digest, migration identity, SBOM, scan results, and policy version into one immutable promotion record.

Image-level runtime tests are also missing for UID, writable paths under read-only rootfs, health/readiness, SIGTERM/drain, worker queue shutdown, and migration behavior. Mutable package-repository upgrade steps weaken reproducibility beyond a digest-pinned base image.

### 4.4 Security, trust, and exposure

The checked-in Kyverno `verifyImages` policy has not been proven against a cluster with positive and negative admission cases. No accepted production trust policy names the Cosign issuer/identity, Rekor dependency, enforcement owner, or exception process. Chart-level NetworkPolicy, explicit service-account/RBAC ownership, default-deny egress, Pod Security/seccomp/capability policy, and service-to-service trust are not evidenced.

Ingress, DNS, TLS issuance/renewal, API-versus-proxy exposure, external/private endpoints, and provider egress boundaries remain undecided. Production credentials, key custody/KMS, rotation, recovery, registry pull access, and emergency access must remain outside Git and need an accountable operational contract.

### 4.5 Recovery, monitoring, and operator evidence

The current recovery evidence does not meet the 4.P.5 gate. The milestone lists **working planning targets**, not accepted or measured results: PostgreSQL ≤5m RPO / ≤30m RTO, ClickHouse ≤24h / ≤60m, Redis as cache/no recovery target, MinIO ≤24h / ≤60m, and outbox RPO 0 by sequence. These targets require owner review and non-vacuous drills; do not report them as achieved.

Backup scheduling, PITR/WAL freshness, encryption/key recovery, retention/immutability, restore order, ClickHouse/object-store recovery, outbox/sink/deletion reconciliation, metrics publication, external alert routing, measured recovery objectives, and on-call escalation are not production-validated. Alertmanager currently routes locally; Helm observability is thinner than the local Compose stack.

## 5. Recommended implementation sequence after G0

This sequence is a proposal based on existing repository boundaries. It does not authorize any deployment. Work must follow the accepted profile and relevant G1–G8 gates; provider-specific work waits for provider/account/region and data-plane decisions.

1. **P0 — G0 contract and profile freeze.** Resolve authority, owners, profile, dependency matrix, trust, environment/Secret contract, migration authority, retention, recovery targets, support boundary, and evidence acceptance rules. No service or data-plane boundary change before this.
2. **P1 — complete service/dependency contract.** Produce one matrix for every workload: ports, readiness dependencies, Postgres/Redis/ClickHouse/S3/queue/provider/Auth/OTLP inputs, Secret references, privilege, egress, writable paths, resource bounds, and owner. Reconcile it against service config and the canonical Console/API runtime.
3. **P2 — close artifact and migration supply chain.** Add the migration image to build/scan/sign/provenance or formally select and test an alternative CI-owned migration mechanism. Gate on exact digests; scan and verify every pushed digest; retain signed provenance/SBOM/scan evidence and bind it to a release manifest. Add non-deploying OCI runtime, health, signal, and migration smoke tests.
4. **P3 — complete chart and security contracts.** Add the accepted Console workload and complete service environment/Secret wiring. Harden the migration Job. Add schema/render checks, default-deny network/RBAC/Pod Security controls, and approved ingress/TLS/egress interfaces. Do not choose a cloud-specific operator or secret controller until its owner decision exists.
5. **P4 — define stateful service and migration operations.** Record, per data class, whether PostgreSQL/pgvector, Redis/queue, ClickHouse, object storage, observability, and KMS are managed externally or platform-owned. Define expand/compatibility/backfill/verify/contract, timeouts, abort/roll-forward, and migration evidence. Keep destructive operations disabled by default.
6. **P5 — recovery and operations.** Build a non-vacuous recovery matrix and evidence format for Postgres/PITR, ClickHouse, object artifacts, Redis projections, keys, outbox sequence/sink watermarks, tenant isolation, and deletion fences. Wire backup freshness and drill-success metrics to the chosen collector; define real alert routing, runbooks, owners, escalation, capacity, and reviewed RPO/RTO/SLO targets.
7. **P6 — no-deploy CI validation.** Exercise lint, chart schema/render, digest/sentinel guards, manifest policy checks, image runtime tests, migration compatibility tests, security scans, and negative cases in CI. Record command/tool versions and source/config/image digests. No workflow that publishes or deploys is needed for this phase.
8. **P7 — separate environment acceptance.** Cluster admission, ingress/TLS, failover, backup/restore, rollout/rollback, paging, and production recovery require a named profile and a separately authorized test environment. They remain unverified under the current no-deploy direction; do not mark production accepted without this evidence.

## 6. No-deploy validation ledger

| Validation | Status in this audit | What remains |
|---|---|---|
| Read-only source/config audit of five infrastructure areas | Completed; independent findings informed the static checker below | Reviewer confirmation of source findings and owner dispositions. |
| Offline production-readiness source audit | Implemented in `.github/scripts/audit-production-readiness.py`; eleven regression tests in `.github/scripts/test-production-readiness-audit.py`; CI repo-guard runs both. Reports ten current residuals as `OPEN`, including a selected service-config/chart env-name matrix; does not render or execute infrastructure and does not accept G0. | Review the findings, correct any changed source assumptions, and update the test baseline as individual gaps are addressed after G0. |
| Helm lint/template, profile regression, production digest guards | Not rerun; Helm was unavailable | Run after G0 in a tool-equipped environment; record versions and output. |
| Docker/Compose or OCI runtime tests | Not run; no Docker/Compose CLI or daemon/socket was available | Build/run only non-deploying test images after the relevant changes and profile are approved. |
| Kubernetes schema/admission, ingress, network, HPA/PDB, rollout/rollback | Not run; no cluster was used | These are environment-level evidence and are incompatible with the current no-deploy authorization. |
| Production migration, PITR/restore, key recovery, live alerts | Not run; no credentials, provider, scheduler, or production/staging system was accessed | Requires owner-approved non-production test profile and explicit future authorization. |
| GitHub release/publish/deploy workflows | Not triggered | Keep disabled from this task; source-level workflow configuration is not execution evidence. |

## 7. Decisions still required

The following cannot be safely invented from the repository or inferred from a general instruction to proceed:

- Actual supported deployment topology (single-node self-hosted versus HA production), cluster ownership, provider/account/region/AZ (intentionally deferred under the selected provider-neutral preparation direction), residency, private networking, and cost envelope.
- Managed versus platform-owned Postgres/pgvector, Redis/queue, ClickHouse, S3-compatible object storage, observability, and KMS/secrets; each needs an owner and recovery boundary.
- Registry and release authority, immutable promotion model, package visibility/retention, supported CPU architectures, signing identity/issuer, Rekor dependency, and vulnerability-exception policy.
- Credential storage and rotation; cryptographic-material recovery; certificate issuance and renewal; ingress ownership; default-deny network controls and destination allowlists; workload identity.
- Migration executor/approver, compatibility window, maintenance policy, abort and roll-forward authority, backup scheduler, data retention/legal hold, and measured recovery targets per data class.
- Named architecture/auth-policy/security/privacy/finance/platform-SRE owners, independent reviewers, on-call/support escalation, and review/expiry dates.

Until those decisions and the required evidence are recorded, the correct status is **prepared for owner review; not accepted, not deployed, and not production-ready**. This plan supersedes the previous local-only task scope but does not supersede the architecture-v2 gates.
