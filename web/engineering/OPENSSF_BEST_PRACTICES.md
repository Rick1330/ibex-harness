# OpenSSF Best Practices (CII) — enrollment and evidence map

OpenSSF Scorecard’s [CII-Best-Practices check](https://github.com/ossf/scorecard/blob/main/docs/checks.md#cii-best-practices) reads the [OpenSSF Best Practices badge](https://www.bestpractices.dev/) API. Enrolling the project raises that Scorecard signal (in-progress → passing → silver → gold).

**Project ID:** [13590](https://www.bestpractices.dev/en/projects/13590)  
**Edit form:** [passing level](https://www.bestpractices.dev/en/projects/13590/passing/edit)

## Maintainer enrollment (one-time)

1. Open the [passing edit form](https://www.bestpractices.dev/en/projects/13590/passing/edit).
2. Set **Project URL** to `https://github.com/Rick1330/ibex-harness` and **website** to `https://ibexharness.com`.
3. Complete criteria using the **Form justification playbook** below (copy URLs verbatim).
4. **Submit often** while editing; save progress before closing the browser.
5. After the project shows **passing**, add the badge to `README.md` (see [Badge after passing](#badge-after-passing)).
6. Re-run the [Scorecard workflow](https://github.com/Rick1330/ibex-harness/actions/workflows/scorecard.yml).

## Evidence map (repo artifacts)

| Best practices theme | IBEX Harness evidence |
| --- | --- |
| Public version control | GitHub repo; Conventional Commits ([CONTRIBUTING.md](../../CONTRIBUTING.md)) |
| Release notes | Root [CHANGELOG.md](../../CHANGELOG.md); [RELEASING.md](./RELEASING.md) |
| API / interface docs | [API reference](https://ibexharness.com/docs/api-reference/chat-completions) |
| Build & test in CI | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) — area gates, unit/integration coverage |
| Vulnerability reporting | [`.github/SECURITY.md`](../../.github/SECURITY.md), security issue template |
| No unfixed critical vulns (process) | Trivy/OSV/govulncheck in CI; Dependabot ([`.github/dependabot.yml`](../../.github/dependabot.yml)) |
| Static analysis | CodeQL, Semgrep, golangci-lint ([ADR-0008](../content/docs/adr/0008-security-ci-gates.mdx)) |
| SBOM / dependency visibility | [`.github/workflows/sbom.yml`](../../.github/workflows/sbom.yml) (Syft + Grype) |
| Signed release artifacts | [`.github/workflows/release.yml`](../../.github/workflows/release.yml) — cosign `*.sig` on SBOM |
| Branch protection | [`.github/branch-protection-main.json`](../../.github/branch-protection-main.json); apply via `infra/scripts/apply-branch-protection.sh` |
| Security policy documented | [SECURITY.md](./SECURITY.md), [ADR-0008](../content/docs/adr/0008-security-ci-gates.mdx) |
| Cryptography | [ADR-0010](../content/docs/adr/0010-cryptography-policy.mdx), `packages/crypto` |

## Branch protection (Scorecard)

Scorecard’s [Branch-Protection check](https://github.com/ossf/scorecard/blob/main/docs/checks.md#branch-protection) expects `main` to require PRs, block force-push, enforce status checks, and (with an admin token) settings such as `enforce_admins` and up-to-date branches.

Apply or refresh settings after changing [`.github/branch-protection-main.json`](../../.github/branch-protection-main.json):

```bash
bash infra/scripts/apply-branch-protection.sh
```

Solo mode keeps **0 required approving reviews** per [ADR-0003](../content/docs/adr/0003-branch-protection-and-merge-policy.mdx); PR + CI gates remain mandatory.

## Signed releases (Scorecard)

The [Signed-Releases check](https://github.com/ossf/scorecard/blob/main/docs/checks.md#signed-releases) inspects the last releases for signature files (`*.sig`, `*.sigstore`, `*.intoto.jsonl`, etc.). Tagged releases (`v*.*.*`) attach a cosign signature for `sbom.spdx.json` (see `release.yml`). Container images use GitHub attestations in `docker-publish.yml`.

After the first semver tag from the version release pipeline, confirm release assets include `sbom.spdx.json.sig`.

## Badge after passing

**Do not add the badge until bestpractices.dev shows passing.** Then add to `README.md`:

```markdown
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/13590/badge)](https://www.bestpractices.dev/projects/13590)
```

---

## Form justification playbook

Copy each **Justification** into the matching criterion on the [passing edit form](https://www.bestpractices.dev/en/projects/13590/passing/edit). Set **Met**, **N/A**, or **Unmet** as indicated. For acceptable deferrals on SHOULD criteria, start justification with `// ` (per badge app rules).

### General project fields

| Field | Value |
| --- | --- |
| Description | Production-grade platform for AI agent memory, context assembly, and secure LLM proxying. Proxies LLM requests, injects persistent memory, and enforces multi-tenant auth with drift detection for enterprise agent fleets. |
| Languages | `Go, Python, TypeScript` |
| License | `MIT` |
| Project URL | `https://ibexharness.com` |
| Repo URL | `https://github.com/Rick1330/ibex-harness` |

### Basics

| Criterion | Status | Justification |
| --- | --- | --- |
| `documentation_interface` | Met | REST and gRPC API reference: https://ibexharness.com/docs/api-reference/chat-completions , https://ibexharness.com/docs/api-reference/errors , https://ibexharness.com/docs/api-reference/auth-grpc . README links: https://github.com/Rick1330/ibex-harness#what-to-read-next |

### Change control

| Criterion | Status | Justification |
| --- | --- | --- |
| `repo_interim` | Met | Public `main` branch contains full development history between releases: https://github.com/Rick1330/ibex-harness/commits/main/ |
| `version_unique` | Met | Semver tags `vMAJOR.MINOR.PATCH` per release; see https://github.com/Rick1330/ibex-harness/releases and https://github.com/Rick1330/ibex-harness/blob/main/web/engineering/RELEASING.md |
| `version_semver` | Met | Semantic Versioning documented in CHANGELOG and RELEASING.md: https://github.com/Rick1330/ibex-harness/blob/main/CHANGELOG.md |
| `version_tags` | Met | Releases identified with git tags `v*.*.*`: https://github.com/Rick1330/ibex-harness/tags |
| `release_notes` | Met | Human-readable release notes: https://github.com/Rick1330/ibex-harness/blob/main/CHANGELOG.md and GitHub Releases https://github.com/Rick1330/ibex-harness/releases |
| `release_notes_vulns` | N/A | No publicly known CVE-assigned vulnerabilities fixed in any release yet. |

### Reporting

| Criterion | Status | Justification |
| --- | --- | --- |
| `report_process` | Met | Bug reports via GitHub Issues and template: https://github.com/Rick1330/ibex-harness/blob/main/.github/ISSUE_TEMPLATE/bug_report.md , https://github.com/Rick1330/ibex-harness/blob/main/CONTRIBUTING.md |
| `report_archive` | Met | Searchable public issue archive: https://github.com/Rick1330/ibex-harness/issues |
| `report_responses` | Met | // Pre-1.0 solo-maintained project with low external issue volume; all filed issues receive maintainer acknowledgment on GitHub. |
| `enhancement_responses` | Met | // Low enhancement volume pre-1.0; maintainer responds to roadmap and issue discussions on GitHub. |
| `vulnerability_report_process` | Met | https://github.com/Rick1330/ibex-harness/blob/main/.github/SECURITY.md |
| `vulnerability_report_private` | Met | Private reporting via GitHub Security Advisories (HTTPS): https://github.com/Rick1330/ibex-harness/security/advisories/new |
| `vulnerability_report_response` | N/A | No vulnerability reports received in the last 6 months. |

### Quality

| Criterion | Status | Justification |
| --- | --- | --- |
| `build_floss_tools` | Met | Makefile and FLOSS toolchains (Go, buf, make, Docker Compose): https://github.com/Rick1330/ibex-harness/blob/main/Makefile |
| `test` | Met | Automated FLOSS test suites documented in CONTRIBUTING: https://github.com/Rick1330/ibex-harness/blob/main/CONTRIBUTING.md#testing-policy ; CI: https://github.com/Rick1330/ibex-harness/actions/workflows/ci.yml |
| `test_invocation` | Met | Standard invocation: `go test ./...`, `make coverage-report` — see CONTRIBUTING testing section. |
| `test_most` | Met | // Coverage tracked in CI (Codecov); critical paths (auth, proxy, tenant isolation) have integration tests with real Postgres. |
| `test_continuous_integration` | Met | CI on every PR to `main`: https://github.com/Rick1330/ibex-harness/actions/workflows/ci.yml |
| `test_policy` | Met | Policy documented: https://github.com/Rick1330/ibex-harness/blob/main/CONTRIBUTING.md#testing-policy and https://github.com/Rick1330/ibex-harness/blob/main/web/engineering/TESTING_STRATEGY.md |
| `tests_are_added` | Met | Recent feature PRs include tests (e.g. OpenAI client, SBOM fixes); enforced in PR template. |
| `tests_documented_added` | Met | CONTRIBUTING and TESTING_STRATEGY require tests for behavior changes. |
| `warnings` | Met | golangci-lint, Semgrep, CodeQL, ruff/bandit, ESLint — see CONTRIBUTING linting section: https://github.com/Rick1330/ibex-harness/blob/main/CONTRIBUTING.md#linting-and-static-analysis |
| `warnings_fixed` | Met | Merge-blocking CI gates; linter failures block merge per CONTRIBUTING. |
| `warnings_strict` | Met | golangci-lint with project `.golangci.yml`; strict Go and TypeScript checks in CI. |

### Security

| Criterion | Status | Justification |
| --- | --- | --- |
| `know_secure_design` | Met | Threat model and Saltzer-Schroeder-style controls: https://github.com/Rick1330/ibex-harness/blob/main/web/engineering/SECURITY.md ; tenant isolation ADRs; fail-closed auth. Primary maintainer completed OpenSSF Secure Software Development Fundamentals. |
| `know_common_errors` | Met | OWASP/CWE mitigations documented (SQL injection via parameterized queries + RLS, authZ denials, secret handling): SECURITY.md and ADR-0008. |
| `crypto_published` | Met | Argon2id, TLS 1.2+; ADR-0010: https://ibexharness.com/docs/adr/0010-cryptography-policy |
| `crypto_call` | Met | `packages/crypto` wraps `golang.org/x/crypto/argon2` and `crypto/rand`; no custom cipher implementations. |
| `crypto_floss` | Met | FLOSS crypto libraries only (Go stdlib + x/crypto). |
| `crypto_keylength` | N/A | Application does not expose configurable asymmetric TLS keys; Argon2id uses 256-bit derived keys per ADR-0010. |
| `crypto_working` | Met | No MD5/SHA-1/RC4/DES for security; Argon2id for secrets per ADR-0010. |
| `crypto_weaknesses` | Met | // TLS cipher suites delegated to deployment (reverse proxy); no SHA-1 for integrity. |
| `crypto_pfs` | Met | // HTTPS/TLS for all distribution; forward secrecy via modern TLS stacks in production. |
| `crypto_password_storage` | Met | Argon2id PHC format for PAT hashes: https://github.com/Rick1330/ibex-harness/tree/main/packages/crypto |
| `crypto_random` | Met | `crypto/rand` via `packages/crypto.GenerateRandomBytes`: ADR-0010. |
| `delivery_unsigned` | Met | Release workflow uses cosign signatures for SBOM; Grype install uses HTTPS + checksum verify (not unsigned http hashes): https://github.com/Rick1330/ibex-harness/blob/main/.github/workflows/release.yml , https://github.com/Rick1330/ibex-harness/blob/main/.github/workflows/sbom.yml |
| `vulnerabilities_fixed_60_days` | Met | No unpatched medium+ CVEs in project code; CI scans (govulncheck, Trivy, OSV, Dependabot) on every change. |
| `vulnerabilities_critical_fixed` | Met | Critical findings block merge or trigger immediate fix per SECURITY.md response expectations. |
| `no_leaked_credentials` | Met | gitleaks in CI on every PR: https://github.com/Rick1330/ibex-harness/actions/workflows/ci.yml |

### Analysis

| Criterion | Status | Justification |
| --- | --- | --- |
| `static_analysis` | Met | CodeQL, Semgrep, golangci-lint run before merge on every PR; release tags require green `main`: https://github.com/Rick1330/ibex-harness/blob/main/.github/workflows/codeql.yml , ADR-0008 |
| `static_analysis_common_vulnerabilities` | Met | Semgrep custom rules + CodeQL security queries + govulncheck. |
| `static_analysis_fixed` | Met | High/critical Semgrep/Trivy findings block merge; Dependabot PRs for CVEs. |
| `static_analysis_often` | Met | Static analysis on every PR (CodeQL, Semgrep, golangci-lint). |
| `dynamic_analysis` | Met | `go test -race` and fuzz smoke in CI: https://github.com/Rick1330/ibex-harness/blob/main/.github/workflows/ci.yml |
| `dynamic_analysis_unsafe` | N/A | Primary implementation languages are Go, Python, and TypeScript (memory-safe). |
| `dynamic_analysis_enable_assertions` | Met | Go tests and fuzz targets run with race detector; test assertions in CI. |
| `dynamic_analysis_fixed` | N/A | No medium+ exploitable issues from dynamic analysis reported to date. |
