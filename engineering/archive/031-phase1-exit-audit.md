# Phase 1 Exit Audit — Detailed Gap Register

**Date:** 2026-06-05  
**Git SHA (`main` at audit start):** `ce3b0bd`  
**Branch:** `test/m1-5-1-security-integration-test-suite`  
**Tracks:** A (security), B (docs/ADR), C (CI), D (code quality), E (ops)

---

## Executive summary

Phase 1 implementation through M1.4.3 is substantively sound: proxy middleware chain, ADR alignment, and per-milestone unit/integration tests are in good shape. The **designed completion gate (M1.5.1)** was not implemented at audit start — ~48% of the 31-case SEC matrix lacked integration coverage, and rate limiting was disabled in the proxy integration fixture via `ratelimit.Noop()`.

This register documents every gap with severity, evidence, remediation, and resolution status.

---

## Severity definitions

| Level | Meaning |
|-------|---------|
| **P0** | Blocker — must be green before Phase 2 |
| **P1** | High — fix at M1.5.1 gate or immediately after |
| **P2** | Hygiene — fix before phase sign-off PR |
| **P3** | Defer — document as Phase 2+; not hidden |

---

## P0 — Blockers

### GAP-001 — M1.5.1 security matrix incomplete

| Field | Value |
|-------|-------|
| **Track** | A |
| **Evidence** | Milestone `1.5.1-security-integration-test-suite.md` status Planned; 15/31 SEC cases missing, 8 partial at audit start |
| **Remediation** | Implement `proxy_security_sec*_test.go` with full SEC-1.x–SEC-6.x matrix |
| **Status** | **Resolved** in M1.5.1 branch |

### GAP-002 — Rate limiting untestable in integration fixture

| Field | Value |
|-------|-------|
| **Track** | A |
| **Evidence** | `proxy_auth_integration_helpers_test.go` — `Limiter: ratelimit.Noop()` |
| **Remediation** | Wire miniredis + `ratelimit.NewRedisSlider` in `startProxyServer` |
| **Status** | **Resolved** in M1.5.1 branch |

### GAP-003 — No `security-integration` required CI check

| Field | Value |
|-------|-------|
| **Track** | C |
| **Evidence** | `branch-protection-main.json` lacks `security-integration`; no job in `ci.yml` |
| **Remediation** | Add CI job + branch protection entry |
| **Status** | **Resolved** in M1.5.1 branch |

### GAP-004 — SEC-6.x envelope gap on agent middleware internal error

| Field | Value |
|-------|-------|
| **Track** | A |
| **Evidence** | `agent_middleware.go:43` — `http.Error` plaintext 500 |
| **Remediation** | Use `apierror.WriteStatus` with `CodeServiceDegraded` |
| **Status** | **Resolved** in M1.5.1 branch |

---

## P1 — High

### GAP-005 — Milestone error code names stale

| Field | Value |
|-------|-------|
| **Track** | A/B |
| **Evidence** | Matrix cites `UNAUTHENTICATED`/`PERMISSION_DENIED`; code uses `MISSING_TOKEN`/`INSUFFICIENT_PERMISSIONS` per ADR-0020 |
| **Remediation** | Update milestone matrix + tests to canonical `packages/apierror` codes |
| **Status** | **Resolved** — matrix updated; production codes unchanged |

### GAP-006 — SECURITY.md rate-limit model wrong

| Field | Value |
|-------|-------|
| **Track** | B |
| **Evidence** | `SECURITY.md` §8.2 claims in-memory fallback; code follows ADR-0015 fail-open |
| **Remediation** | Rewrite §8.2 to Phase 1 org RPM + fail-open |
| **Status** | **Resolved** in docs PR |

### GAP-007 — Missing SEC seed scenarios

| Field | Value |
|-------|-------|
| **Track** | A/D |
| **Evidence** | No `SeedTokenExpired`, `SeedAgentWithStatus(archived)`, `SeedTokenZeroPerms` |
| **Remediation** | Add testutil helpers + SEC-1.6, SEC-2.6, SEC-5.1 tests |
| **Status** | **Resolved** in M1.5.1 branch |

### GAP-008 — phase-1 README / CURRENT_STATE stale

| Field | Value |
|-------|-------|
| **Track** | B |
| **Evidence** | README shows M1.3.2 Next, M1.4.x Planned; CURRENT_STATE SHA `d366743` vs `ce3b0bd` |
| **Remediation** | Docs sync in sign-off PR |
| **Status** | **Resolved** in sign-off PR |

---

## P2 — Hygiene

### GAP-009 — `-race` not in CI

| Field | Value |
|-------|-------|
| **Track** | C |
| **Evidence** | `TESTING_STRATEGY.md:118` claims CI race; `ci.yml` has no `-race` |
| **Remediation** | Add `go-race` job |
| **Status** | **Resolved** in CI hygiene |

### GAP-010 — golangci skips `packages/`

| Field | Value |
|-------|-------|
| **Track** | C |
| **Evidence** | `ci.yml` — only auth + proxy |
| **Remediation** | Extend to `./packages/...` |
| **Status** | **Resolved** in CI hygiene |

### GAP-011 — API/ENV docs oversell Phase 1

| Field | Value |
|-------|-------|
| **Track** | B |
| **Evidence** | `API_DOCUMENTATION.md` full platform; `ENVIRONMENT_VARIABLES.md` REDIS_URL required for auth |
| **Remediation** | Phase banners + conditional REDIS_URL |
| **Status** | **Resolved** in docs PR |

### GAP-012 — Phase 1 exit criteria unchecked

| Field | Value |
|-------|-------|
| **Track** | B |
| **Evidence** | `phase-1-core-platform/README.md:60-67` all `[ ]` |
| **Remediation** | Check after M1.5.1 green |
| **Status** | **Resolved** in sign-off PR |

---

## P3 — Deferred (explicit)

| Item | Rationale |
|------|-----------|
| JWT / dashboard sessions | Phase 2+ |
| LLM forwarding, Python services | Phase 2+ |
| Coverage percentage CI gate | Phase 2.6.1 / later |
| In-memory rate-limit fallback | Not in ADR-0015; would need new ADR |
| Fuzzing / penetration testing | Out of M1.5.1 scope |
| CodeScene as merge gate | Advisory only |

---

## Track A — SEC matrix at audit start

| ID | Status (audit) | Resolution |
|----|----------------|------------|
| SEC-1.1 | Partial | Full assert `MISSING_TOKEN` |
| SEC-1.2 | Missing | Empty Bearer test |
| SEC-1.3 | Partial | Malformed token test |
| SEC-1.4 | Partial | Unknown token test |
| SEC-1.5 | Partial | Revocation + timing |
| SEC-1.6 | Missing | `SeedTokenExpired` |
| SEC-1.7 | Covered | Retained |
| SEC-2.1 | Covered | Retained |
| SEC-2.2 | Missing | Invalid UUID |
| SEC-2.3 | Missing | Random UUID not in DB |
| SEC-2.4 | Covered | Retained |
| SEC-2.5 | Covered | Retained |
| SEC-2.6 | Missing | Archived agent |
| SEC-2.7 | Covered | Retained |
| SEC-3.1 | Covered | Retained |
| SEC-3.2 | Covered | Retained |
| SEC-3.3 | Missing | Reverse cross-org |
| SEC-3.4 | Missing | Timing delta |
| SEC-4.1–4.5 | Missing | Real Redis limiter |
| SEC-5.1 | Missing | Zero permissions |
| SEC-5.2 | Partial | Read-only on chat |
| SEC-5.3 | Covered | Retained |
| SEC-6.1–6.5 | Missing/partial | Systematic envelope suite |

---

## Track B — ADR fidelity (0011–0022)

| ADR | Status at audit | Notes |
|-----|-----------------|-------|
| 0011 | Implemented | Proxy auth client |
| 0012 | Implemented | Request normalization |
| 0013 | Implemented | Error envelope (GAP-004 fixed) |
| 0014 | Implemented | Domain migration sequencing |
| 0015 | Implemented | Rate limit skeleton; doc drift GAP-006 |
| 0016 | Implemented | Agent verification |
| 0017 | Implemented | Request ID |
| 0018 | Implemented | Graceful shutdown |
| 0019 | Implemented | OTel providers |
| 0020 | Implemented | Shared packages |
| 0021 | Implemented | Prometheus metrics |
| 0022 | Implemented | Health check contract |

---

## Track C — CI inventory at audit

**Required (10):** repo-guards, markdownlint, gitleaks, CodeQL, trivy, osv-scan, semgrep, golangci-lint, bandit, hadolint

**Informational:** go-services, db-migrate-smoke, proto-contract, auth-validate-smoke, proxy-auth-smoke, proxy-agent-verify-smoke, buf-lint, scorecard, sbom

**Added by remediation:** security-integration, go-race; golangci extended to packages/

---

## Track D — Code quality positives

- All 12 `packages/*` have `_test.go` coverage
- Middleware chain order verified in `router_protected.go`
- Cross-org agent → 403 (not 404)
- Structured logging + OTel + metrics adopted in auth/proxy

---

## Track E — Ops validation

| Check | Result |
|-------|--------|
| `/health` always 200 | Per ADR-0022 unit tests |
| `/ready` parallel checkers | auth: postgres+grpc; proxy: auth_grpc+redis |
| OPS_GUIDE K8s probes | Documented |
| Shutdown hook ordering | OTel registered first per ADR-0018 |

---

## Sign-off criteria (post-remediation)

- [x] Gap register complete (this document)
- [x] Repo summary `PHASE1_EXIT_AUDIT.md` published
- [x] Zero open P0 gaps
- [x] All 31 SEC cases pass with `-tags=integration`
- [x] `security-integration` CI required on `main`
- [x] P1 gaps closed
- [x] CURRENT_STATE reflects Phase 1 complete
