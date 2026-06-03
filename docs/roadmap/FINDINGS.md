# Findings Log

Unexpected discoveries, design pivots, and plan changes. Update this file when implementation reveals something the roadmap did not anticipate.

## Template (copy for new entries)

```markdown
## YYYY-MM-DD — [Brief title]

**Context:** Phase N / Milestone N.M.K

**Finding:** What we discovered.

**Impact:** How this changes scope, order, or estimates.

**Decision:** What we are doing about it.

**Updated:** Which roadmap files changed (paths).
```

---

## 2026-06-01 — Roadmap published under docs/roadmap/

**Context:** Post Foundation-004 closure

**Finding:** Foundation work split across stacked PRs (#6 toolchain, #7/#8 skeletons) caused branch drift and duplicate CI jobs when Go work landed on the toolchain branch.

**Impact:** Roadmap process must keep toolchain-only PRs free of service code; rebase feature branches onto `main` after each phase merge.

**Decision:** Document in phase-0 lessons; use `CURRENT_STATE.md` as single source for "what's next."

**Updated:** `docs/roadmap/README.md`, `phase-0-foundation/lessons-learned.md`

---

## 2026-06-01 — Single root Go module adopted

**Context:** Foundation-004 / Phase 0

**Finding:** Per-service `go.mod` files increase drift; monorepo benefits from one module early.

**Impact:** All Go services import `github.com/Rick1330/ibex-harness/...`; Docker builds from repo root.

**Decision:** Keep one root `go.mod`; revisit only via ADR if a service must version independently.

**Updated:** `docs/FILE_STRUCTURE.md`, Report 005 (local)

---

## 2026-06-01 — Auth proto does not exist yet

**Context:** Phase 1 planning

**Finding:** Only `ibex.context.v1` exists in `packages/proto`. Architecture assumes proxy → auth gRPC validation.

**Impact:** Milestone 1.1.2 must add `ibex.auth.v1` before proxy auth client (1.2.1).

**Decision:** Schedule auth proto milestone before auth validation and proxy integration.

**Updated:** `phase-1-core-platform/goals.md`, milestone prerequisites

---

## 2026-06-03 — OpenSSF Scorecard alerts triaged (not product CVEs)

**Context:** Post StepSecurity [PR #33](https://github.com/Rick1330/ibex-harness/pull/33) merge

**Finding:** GitHub Code Scanning showed ~30 open **Scorecard** supply-chain policy alerts (pinned dependencies, code review, fuzzing, SAST maturity)—not exploitable application findings. Grype had a stale failed analysis from pre–PR #31 SARIF upload; SBOM workflow is artifact-only per ADR-0008.

**Impact:** Security tab noise obscured real gates (CodeQL, Semgrep, Trivy, OSV). Solo-maintainer repo will not satisfy every Scorecard recommendation without explicit policy choices.

**Decision:** Delete stale Grype analysis on `main`; dismiss fixed `PinnedDependencies` alerts after pinned SHAs landed; dismiss CodeReview/Fuzzing/SAST/CII alerts as not applicable or tracked as backlog. Grype remains workflow artifacts only (`grype-report.txt/json`).

**Updated:** `CONTRIBUTING.md`, `docs/roadmap/CURRENT_STATE.md`, workspace archive 010
