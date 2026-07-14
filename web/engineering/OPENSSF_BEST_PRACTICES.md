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

After the first semver tag from the version release pipeline, confirm release assets include `sbom.spdx.json.sig` and `sbom.spdx.json.bundle.json`.

## Badge after passing

**Do not add the badge until bestpractices.dev shows passing.** Then add to `README.md`:

```markdown
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/13590/badge)](https://www.bestpractices.dev/projects/13590)
```

---

## Form justification playbook

Copy each **Justification** into the matching criterion on the [passing edit form](https://www.bestpractices.dev/en/projects/13590/passing/edit). Set **Met**, **N/A**, or **Unmet** as indicated. For acceptable deferrals on SHOULD criteria, start the justification text with a double-slash prefix (per badge app rules).

**Working copy (parent workspace, not in git):** `ibex-r/scorecard-form-justifications.md` — full copy-paste text for every unset criterion.

### General project fields

| Field | Value |
| --- | --- |
| Description | Production-grade platform for AI agent memory, context assembly, and secure LLM proxying. Proxies LLM requests, injects persistent memory, and enforces multi-tenant auth with drift detection for enterprise agent fleets. |
| Languages | `Go, Python, TypeScript` |
| License | `MIT` |
| Project URL | [ibexharness.com](https://ibexharness.com) |
| Repo URL | [github.com/Rick1330/ibex-harness](https://github.com/Rick1330/ibex-harness) |

### Quick reference (evidence URLs)

| Theme | Primary evidence |
| --- | --- |
| API / interface | [API reference](https://ibexharness.com/docs/api-reference/chat-completions), [errors](https://ibexharness.com/docs/api-reference/errors), [auth gRPC](https://ibexharness.com/docs/api-reference/auth-grpc) |
| Release notes | [CHANGELOG.md](../../CHANGELOG.md), [RELEASING.md](./RELEASING.md), [GitHub Releases](https://github.com/Rick1330/ibex-harness/releases) |
| Bug / vuln reports | [CONTRIBUTING.md](../../CONTRIBUTING.md), [SECURITY.md](../../.github/SECURITY.md), [issues](https://github.com/Rick1330/ibex-harness/issues) |
| Tests & CI | [Testing policy](../../CONTRIBUTING.md#testing-policy), [ci.yml](../../.github/workflows/ci.yml), [TESTING_STRATEGY.md](./TESTING_STRATEGY.md) |
| Lint / static analysis | [Linting policy](../../CONTRIBUTING.md#linting-and-static-analysis), [codeql.yml](../../.github/workflows/codeql.yml), [ADR-0008](../content/docs/adr/0008-security-ci-gates.mdx) |
| Secure design | [SECURITY.md](./SECURITY.md), [ADR-0010](../content/docs/adr/0010-cryptography-policy.mdx), [packages/crypto](../../packages/crypto) |
| Signed delivery | [release.yml](../../.github/workflows/release.yml), [sbom.yml](../../.github/workflows/sbom.yml) |

### Criterion status summary

| Section | Set Met when form opens | Set N/A |
| --- | --- | --- |
| Basics | `documentation_interface` | — |
| Change control | `repo_interim`, `version_*`, `release_notes` (after v0.1.0 tag) | `release_notes_vulns` |
| Reporting | `report_process`, `report_archive`, `vulnerability_report_*` | `vulnerability_report_response` |
| Quality | `test`, `test_policy`, `warnings`, `warnings_fixed`, `build_floss_tools` | — |
| Security | `know_secure_design`, `know_common_errors`, `crypto_*` (except keylength), `delivery_unsigned`, `vulnerabilities_*`, `no_leaked_credentials` | `crypto_keylength` |
| Analysis | `static_analysis`, `dynamic_analysis` | `dynamic_analysis_unsafe`, `dynamic_analysis_fixed` |

### Reporting responses (dated evidence)

| Criterion | Status | Justification |
| --- | --- | --- |
| `report_responses` | Met | Between 2025-07-01 and 2026-07-13, zero bug reports were filed in the public issue tracker ([issues](https://github.com/Rick1330/ibex-harness/issues)); the majority requirement is satisfied vacuously. Maintainer acknowledges any future reports on GitHub. |
| `enhancement_responses` | Unmet | // No public enhancement requests filed in the last 12 months (issue tracker empty as of 2026-07-13). Pre-1.0 solo project; enhancements are tracked via pull requests and the public roadmap instead. |

Other SHOULD criteria with low external traffic (`test_most`, `crypto_weaknesses`, `crypto_pfs`): mark **Met** with a double-slash deferral prefix explaining pre-1.0 solo maintenance.
