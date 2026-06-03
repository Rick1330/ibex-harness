# IBEX Harness — Dependencies

## 1) Purpose

This document defines:

- how we decide whether to add a dependency,
- how we keep dependencies secure and up to date,
- how we prevent “dependency bloat” (especially in SDKs and hot paths),
- and the initial dependency inventory by service/module.

IBEX Harness is a long-lived, security-sensitive system. Dependencies are a major source of:

- supply-chain compromise risk,
- hidden transitive bloat,
- build instability,
- performance regressions,
- and maintenance debt.

**Policy:** Adding a dependency is an architectural decision, not a convenience.

---

## 2) Dependency Selection Philosophy

### 2.1 Core principles

1. **Prefer standard libraries first**
   - If the standard library can do it safely and clearly, use it.
2. **Minimize transitive dependencies**
   - A “small” dependency can pull in 50+ transitive dependencies.
3. **Stability over novelty**
   - Prefer mature libraries with stable APIs and strong adoption.
4. **Security posture matters**
   - A library with frequent CVEs or unclear maintainership is not acceptable.
5. **Operational simplicity**
   - Avoid dependencies that require new runtime services unless justified.
6. **SDKs must be ultra-minimal**
   - SDK dependency bloat becomes *your users’ problem*.

### 2.2 Special rules for hot paths

For latency-critical paths (proxy, context assembly):

- dependencies must justify themselves with measurable value
- avoid frameworks and heavy abstractions
- prefer explicit code over “magic” libraries that add hidden overhead

---

## 3) Dependency Admission Process (Required)

No dependency can be added without completing this checklist in the PR description.

### 3.1 Admission checklist (must be answered)

For dependency: **`<name>`** (version **`<x.y.z>`**)

1) **Why is it needed?**

   - What exact problem does it solve?
   - What is the alternative using stdlib or existing deps?

2) **Scope**

   - Which service(s) / package(s) will use it?
   - Is it in a hot path? (proxy/context/auth)

3) **Security**

   - Known CVEs in last 24 months?
   - Security advisories policy / response track record?
   - Does it handle untrusted input? (parsers, template engines)

4) **Maintenance & maturity**

   - Maintained in last 6 months?
   - Bus factor (how many maintainers)?
   - Adoption (is it widely used in production?)

5) **Transitive dependency cost**

   - How many transitive dependencies?
   - What licenses are introduced?
   - Does it increase bundle size (TypeScript)?

6) **Performance**

   - Any expected runtime cost (allocations, reflection, async overhead)?
   - If in hot path, show micro-benchmark or rationale.

7) **License**

   - Must be compatible with our repo license strategy.
   - Disallowed licenses are listed below.

8) **Exit strategy**

   - If this dependency is abandoned, what do we do?
   - Can we replace it without rewriting the system?

### 3.2 Approval rules

- Non-hot path dependency: 1 maintainer approval
- Hot path dependency (proxy/auth/context): 2 approvals + performance review
- Any security/auth/crypto dependency: security review required
- Any new runtime service (Kafka, new DB, etc.): ADR required

---

## 4) Lockfiles, Reproducibility, and Tooling

### 4.1 Go

- `go.mod` + `go.sum` are required and committed.
- Use `govulncheck` in CI.
- Prefer minimal dependencies; avoid “helper” packages that add little value.

### 4.2 Python

- Use `uv` for dependency management.
- `pyproject.toml` declares direct dependencies.
- `uv.lock` must be committed for reproducibility.
- Use `pip-audit` or `uv pip audit` + OSV scanning in CI.

### 4.3 TypeScript

- We must choose and standardize one package manager.
  - Default: **npm** + `package-lock.json` (consistent with early docs).
  - If switching to pnpm for monorepo performance, create an ADR and migrate fully.
- Lockfile must be committed.
- Use `npm audit` (or `pnpm audit`) plus OSV scanning in CI.

### 4.4 Docker base images

- Pin base images by digest in production builds where feasible.
- Scan images with Trivy in CI.
- Maintain a documented baseline set of images (see Section 10).

---

## 5) Security & Update Policy

### 5.1 Update cadence

- Patch updates: weekly (automated PRs via Dependabot/Renovate)
- Minor updates: monthly (or bundled with planned work)
- Major updates: explicit evaluation + ADR if risk is meaningful

### 5.2 Vulnerability remediation SLAs

| Severity | Example | SLA | Notes |
|----------|---------|-----|-------|
| Critical | remote code execution, auth bypass | 24–48 hours | Emergency patch release allowed |
| High | serious data leak risk | 7 days | Must be prioritized |
| Medium | limited scope issue | 30 days | Planned |
| Low | minor issues | best effort | Prefer batch updates |

### 5.3 When a dependency becomes unsafe

If a library is:

- unmaintained,
- repeatedly vulnerable,
- or introduces unacceptable risk,

We must:

1. freeze updates (pin version)
2. reduce usage surface
3. plan replacement (issue + timeline)
4. consider forking only if replacement is impossible and maintenance is feasible

---

## 6) License Policy

### 6.1 Allowed licenses (typical)

- MIT
- Apache-2.0
- BSD-2-Clause / BSD-3-Clause
- ISC
- Python Software Foundation License

### 6.2 Disallowed / restricted licenses (default)

- GPL / AGPL (unless explicitly approved for isolated tools)
- “Commons Clause” or non-commercial restrictions
- unclear/custom licenses

If a dependency introduces a restricted license, an ADR is required.

---

## 7) Minimal Dependency Targets (by module type)

### 7.1 SDKs (hard limit)

SDKs are user-facing libraries. Dependency bloat is unacceptable.

Targets:

- Python SDK: ≤ 5 dependencies (excluding typing-extensions)
- TypeScript SDK: ideally 0 runtime deps (types/build deps allowed)
- Go SDK: stdlib + gRPC only

### 7.2 Proxy/auth (Go hot path)

Targets:

- avoid frameworks
- avoid heavy logging libraries (use stdlib `slog`)
- keep concurrency and HTTP stack explicit

### 7.3 Dashboard

Targets:

- avoid heavy UI frameworks beyond Next.js + Tailwind
- avoid large chart libs unless justified (bundle size budgets)
- do not introduce “utility” libs for trivial helpers (prefer small local helpers)

---

## 8) Initial Dependency Inventory (Planned Baseline)

This section defines the intended baseline dependency set. If implementation chooses differently, update this file and justify in PR/ADR.

### 8.1 Go — Proxy service (services/proxy)

Required:

- Go stdlib (`net/http`, `context`, `crypto/*`, `encoding/json`, `time`, etc.)
- `google.golang.org/grpc` (if proxy needs gRPC client)
- Prometheus client for Go (metrics)
- OpenTelemetry Go SDK (tracing)

Allowed if justified (hot path review required):

- `fasthttp` (provider-facing client side only) — only with benchmark justification
- `golang.org/x/sync/errgroup` — accepted (small, stable)

Avoid / disallow by default:

- Gin/Echo/Fiber (frameworks)
- heavyweight middleware frameworks
- reflection-heavy routing libraries

### 8.2 Go — Auth service (services/auth)

Required:

- Go stdlib
- JWT library (if not using a minimal, audited implementation)
  - Must be widely used and security-reviewed
- Argon2 implementation (usually `golang.org/x/crypto/argon2`)
- Prometheus + OpenTelemetry

Avoid:

- custom JWT parsing/signing
- custom crypto helpers

### 8.3 Python — Memory/API/Context/Embedder/Worker services

Required (typical):

- FastAPI (API services)
- Uvicorn/Gunicorn (runtime)
- SQLAlchemy 2.0 + async driver (`asyncpg`)
- Pydantic v2 (+ pydantic-settings)
- Redis client (async)
- Celery (worker)
- sentence-transformers / transformers (embedder/extraction)
- numpy/scipy (ranking/statistics) where required
- OpenTelemetry Python SDK
- Sentry SDK

Avoid:

- large “all-in-one” frameworks that add unrelated functionality
- ORMs for ClickHouse (raw SQL preferred)

### 8.4 TypeScript — Dashboard (services/dashboard)

Required:

- Next.js
- React
- TypeScript
- Tailwind
- TanStack Query
- Zustand
- Sentry (optional)
- Observable Plot / Recharts (as needed)

Avoid:

- lodash (prefer native JS)
- moment (prefer date-fns or Temporal polyfill if truly needed)
- axios (prefer fetch)

---

## 9) Dependency Scanning in CI (Required Gates)

### 9.0 Unified scanning (active)

- **OSV Scanner** (`osv-scan` in `.github/workflows/ci.yml`): recursive scan of `go.sum` and future lockfiles; fails on CRITICAL/HIGH; SARIF to GitHub Security.
- **Dependabot** (`.github/dependabot.yml`): `github-actions` + root `gomod` at `/` (weekly). Automated dependency PRs are the primary CVE remediation between CI runs.

**Enable when services land** (uncomment blocks in `.github/dependabot.yml`):

| Ecosystem | Directory | Prerequisite |
|-----------|-----------|--------------|
| `pip` | `/services/memory` | `requirements.txt` or `pyproject.toml` + lockfile |
| `npm` | `/services/dashboard` | `package-lock.json` |

Also add `services/memory` to the Bandit CI job and extend golangci-lint paths for new Go services (see `prompts/05-new-service-bootstrap.txt`).

### 9.1 Go

- OSV Scanner (replaces separate `govulncheck` in CI)
- `golangci-lint` on `./services/auth/...` and `./services/proxy/...` (hard gate)

### 9.2 Python

- Bandit on `services/memory/` when present (HIGH confidence + HIGH severity)
- Semgrep `p/python` + `.semgrep/rules/` (active in CI)
- Future: uncomment Dependabot `pip` entry when memory service has a lockfile

### 9.3 Node/TypeScript

- CodeQL `javascript` + Semgrep `p/typescript` (active)
- Future: uncomment Dependabot `npm` when dashboard has `package-lock.json`

### 9.4 Containers

- **Trivy filesystem** scan on PR/push (`trivy` job): CRITICAL/HIGH, `ignore-unfixed: true`
- **Hadolint** on all `Dockerfile*` paths
- **Future:** `trivy image` per built image when CI produces tagged images (see `.github/workflows/sbom.yml` for SBOM supply chain)
- block critical CVEs unless explicitly waived with documented reason and deadline (ADR required)

---

## 10) Base Image Policy (Docker)

Recommended baseline images:

- Go build: `golang:1.21` (builder stage)
- Go runtime: `gcr.io/distroless/static-debian11` (runtime stage)
- Python runtime: `python:3.11-slim` (or distroless python if feasible)
- Node build: `node:18-alpine` (build stage)
- Node runtime (dashboard): `node:18-alpine` or Next.js recommended runtime

Rules:

- keep runtime images minimal
- remove build tools from runtime
- do not run as root in production images
- pin image versions and consider digest pinning for prod

---

## 11) Documentation Requirements (Dependency Changes)

Whenever a dependency is added/removed/majorly updated:

- update this file (DEPENDENCIES.md)
- update service README if it changes setup
- update any ADR if it changes architecture
- ensure CI scanning rules reflect the new dependency ecosystem

---

## 12) Common Failure Modes (and how we avoid them)

1. **“Just add lodash”** → bundle bloat, security exposure
   - policy: prefer local helpers

2. **“Let’s add Kafka”** → operational complexity early
   - policy: new runtime services require ADR + clear scaling justification

3. **“Let’s add a convenient auth library”** → hidden security pitfalls
   - policy: auth/crypto deps require security review

4. **“Let’s add an ORM for ClickHouse”** → performance/expressiveness loss
   - policy: raw SQL preferred for OLAP queries

5. **SDKs pulling large deps** → user pain + conflicts
   - policy: strict SDK dependency cap

---

Dependencies are a long-term commitment.
The cheapest dependency is the one you never add.
