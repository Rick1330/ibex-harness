# PR2 Final Validation and Evidence Report

## Executive result

Local validation of the PR #900 remediation passes the primary API, Go, web, and repository checks. The API suite passes **693 tests with 10 skips** at **97.42% total coverage**, above the 95% gate. Diff coverage is **100% of 444 changed API lines**. Repository-wide `go test ./...` and `go vet ./...` pass after the final Go sweep exposed and led to fixes for two additional downstream compatibility issues. Web typecheck, tests, and the static build pass. Repository guards, DCO, workflow syntax, shell lint, and aggregate-gate regression cases pass.

These results are local evidence, not a claim that hosted CI or hosted static analyzers passed. The recorded GitHub run is an earlier run on the pre-remediation head [1]. This remediation was assembled on top of that checked-out head and must be validated by the new hosted run triggered by delivery to the PR branch. SonarQube and CodeScene have not been rerun at the final PR head.

## Scope and commit context

The branch is `fix/IBEX-PR2-mounted-identity-authorization-assurance`. The verified base is `origin/main` at `df657fd2436b6d7646b9c491b429a23634d22750`. This remediation was built on the previous local head `fc7b46db96378a52f004d707699c8fab453e250d`. It comprises **38 tracked files**: source, tests, workflow/security checks, configuration documentation, and this report. `AGENTS.md` was not modified.

The new remediation commit uses the requested identity, `elshaday mengesha <elishum8@gmail.com>`, and includes a `Signed-off-by` trailer. The existing PR commit range also passes the repository DCO guard. The branch was pushed to the existing PR branch; no repository settings or branch-protection configuration were changed.

## Final local validation matrix

| Area | Command or check | Result |
|---|---|---|
| API unit and mounted tests | `pytest -q --cov=app --cov-report=term-missing --cov-report=xml:coverage-api.xml` in `services/api` | **693 passed, 10 skipped**; total coverage **97.42%**; configured 95% threshold passed. One dependency deprecation warning from Starlette/httpx remains; no unawaited-queue warning was emitted. |
| Changed API lines | `diff-cover services/api/coverage-api.xml --compare-branch=origin/main --fail-under=95` | **100%**; 444 changed lines, zero uncovered. |
| API lint | `ruff check app tests` | Pass. |
| Repository Go packages | `go test ./...` | Pass. The final sweep found two additional failures outside the originally changed packages; both were repaired. |
| Go static analysis | `go vet ./...` | Pass. |
| Go lifecycle and proxy validation | `bash infra/scripts/verify_phase25.sh`; AuthService/proxy tests and race checks | Pass. AuthService session/JTI race tests and proxy client compile checks also pass. |
| Protobuf | `buf lint`, scoped breaking check, and `buf generate` | Pass; generated outputs used for validation remain uncommitted. |
| Web | `pnpm --filter web typecheck && pnpm --filter web test && pnpm web:build:clean` | Pass; 59 test files and 182 tests passed; static build completed. The build restored its temporarily stashed API route directory, and generated TypeScript files were restored. |
| Repository guards | Repo layout, required-context inventory, Helm profile, landing assets, static export, credential-schema leak, action pin, DCO, and PR tracking checks | Pass. PR #900 tracks issue #899 with required templates and reciprocal references. |
| Aggregate-gate behavior | `bash .github/scripts/test-ci-gate.sh` | All success, skipped, failure, cancellation, unknown-state, and inactive-area cases pass. |
| Workflow and shell lint | `actionlint` on repository workflows; ShellCheck on repository scripts | Pass. |
| Other security and documentation checks | Custom Semgrep workflow-equivalent mode, Gitleaks working-tree scan, Markdown lint, and Helm chart checks | Pass. |
| Whitespace and DCO | `git diff --check`; `.github/scripts/check-dco-signoff.sh` over the PR commit range | Pass. |

## Review and CI finding reconciliation

The operator-session boundary now uses one verifier for Platform and SSE routes. Non-development sessions use AuthService-backed validation, and startup rejects implicit development defaults or incomplete staging/production requirements. Logout verifies access and refresh proofs independently, requires consistent session/family identity when both are supplied, supports refresh-proof revocation, and clears session cookies on success and failure. Step-up feature and permission gates run before consuming a single-use proof. Route policy data is generated into a separate module so regeneration cannot overwrite maintained verifier helpers; traversal and exact-guard branches have targeted tests.

The original repository-guard failure passes its local reproduction. API unit, total-coverage, and changed-line coverage gates pass locally. The phase-verification compile failure was fixed in its proxy mock. A broader Go sweep additionally found that `packages/healthcheck` lacked stubs for the new AuthService client methods and that the protobuf contract test still expected the old RPC count; both were corrected, and the full Go test/vet commands now pass. The original web aggregate's child was skipped because repository guards failed; the corresponding web typecheck, tests, and build now pass locally. Aggregate shell tests continue to fail closed when a child fails or is skipped.

The local analyzer results are not substitutes for hosted analysis. SonarQube and CodeScene were not run on the delivered PR head, so no exact-head analyzer pass is claimed.

## Live and hosted evidence still outstanding

The sandbox has no Docker or Podman. PostgreSQL 16.15 and Redis 7.0.15 are installed and reachable, but PostgreSQL has no CI-style `ibex` role/database and does not expose the `vector` extension. The exact migration/pgvector integration jobs were therefore not reproduced against an equivalent database. Redis connectivity was verified, but the local race tests do not establish multi-replica behavior against a shared deployment.

Live AuthService/API/Redis/PostgreSQL integration, two-replica revocation visibility, real-browser cookie/CSRF/Origin/SSE behavior, and staging or production rollout remain unverified. These require an environment with the CI database extensions, service topology, credentials, and browser/Ingress access. Protected hosted CI and exact-head SonarQube/CodeScene results remain the authoritative next checks after the push [1] [2].

## References

[1]: https://github.com/Rick1330/ibex-harness/actions/runs/36123918689 "Original PR 900 CI run"
[2]: https://github.com/Rick1330/ibex-harness/pull/900 "Pull request 900"
[3]: https://github.com/Rick1330/ibex-harness/issues/899 "Tracked implementation issue 899"
