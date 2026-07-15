# OpenSSF Best Practices — enrollment and evidence map

OpenSSF Scorecard’s [CII-Best-Practices check](https://github.com/ossf/scorecard/blob/main/docs/checks.md#cii-best-practices) reads the [OpenSSF Best Practices badge](https://www.bestpractices.dev/) API.

**Project ID:** [13590](https://www.bestpractices.dev/en/projects/13590)

| Badge level | Status | Edit form |
| --- | --- | --- |
| **Passing** (CII) | **Earned** | [passing/edit](https://www.bestpractices.dev/en/projects/13590/passing/edit) |
| **Baseline Level 1** | In progress | [baseline-1/edit](https://www.bestpractices.dev/en/projects/13590/baseline-1/edit) |
| **Baseline Level 2** | In progress | [baseline-2/edit](https://www.bestpractices.dev/en/projects/13590/baseline-2/edit) |
| **Baseline Level 3** | In progress | [baseline-3/edit](https://www.bestpractices.dev/en/projects/13590/baseline-3/edit) |

**Maintainer-only working material (not in git, not primary evidence):** local `ibex-r/baseline-form-*.md` and `ibex-r/scorecard-form.md` are copy-paste helpers for filling bestpractices.dev. Cite only repository files below when answering badge criteria.

## README badges

Passing badge (merged):

```html
<a href="https://www.bestpractices.dev/projects/13590"><img alt="OpenSSF Best Practices" src="https://www.bestpractices.dev/projects/13590/badge"></a>
```

Baseline badge (after baseline criteria are met):

```markdown
[![OpenSSF Baseline](https://www.bestpractices.dev/projects/13590/baseline)](https://www.bestpractices.dev/projects/13590)
```

After badge-level changes land on `main`, Scorecard refreshes on the next push to `main` or the weekly schedule in [`.github/workflows/scorecard.yml`](../../.github/workflows/scorecard.yml) (Monday 06:00 UTC). There is no `workflow_dispatch` trigger today.

---

## Evidence map (repo artifacts)

| Theme | IBEX Harness evidence |
| --- | --- |
| Public version control | GitHub repo; Conventional Commits ([CONTRIBUTING.md](../../CONTRIBUTING.md)) |
| Governance | [GOVERNANCE.md](./GOVERNANCE.md) — members, roles, access review |
| Release notes | [CHANGELOG.md](../../CHANGELOG.md); [RELEASING.md](./RELEASING.md) |
| Release verification | [RELEASING.md § Verify release integrity](./RELEASING.md#verify-release-integrity-and-authenticity) |
| API / interface docs | [API reference](https://ibexharness.com/docs/api-reference/chat-completions) |
| Build & test in CI | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) |
| DCO / legal sign-off | [CONTRIBUTING.md § DCO](../../CONTRIBUTING.md#developer-certificate-of-origin-dco); [check-dco-signoff.sh](../../.github/scripts/check-dco-signoff.sh) |
| Vulnerability reporting | [`.github/SECURITY.md`](../../.github/SECURITY.md), [GOVERNANCE.md §6](./GOVERNANCE.md#6-vulnerability-disclosure-and-publication-osps-vm-0401) |
| Dependencies | [DEPENDENCIES.md](./DEPENDENCIES.md) |
| SCA / SAST policy | [DEPENDENCIES.md §9.0.1–9.0.2](./DEPENDENCIES.md#901-sca-remediation-thresholds-osps-vm-05010503) |
| SBOM | [`.github/workflows/sbom.yml`](../../.github/workflows/sbom.yml); release SBOM on tags |
| Signed release artifacts | [`.github/workflows/release.yml`](../../.github/workflows/release.yml) — cosign `sbom.spdx.json.sigstore` |
| Branch protection | [`.github/branch-protection-main.json`](../../.github/branch-protection-main.json) |
| Security model | [SECURITY.md](./SECURITY.md), [ADR-0008](../content/docs/adr/0008-security-ci-gates.mdx) |

---

## Baseline criteria quick reference

### Level 1 (24 criteria) — primary evidence

| ID | Met? | Primary URL |
| --- | --- | --- |
| OSPS-AC-01.01 | External | GitHub org MFA — [GOVERNANCE.md §3](./GOVERNANCE.md#3-permission-escalation-review-osps-gv-0401) |
| OSPS-AC-02.01 | External | Org default Read permission — GOVERNANCE §3 |
| OSPS-AC-03.01, 03.02 | Met | [branch-protection-main.json](../../.github/branch-protection-main.json) |
| OSPS-BR-01.01, 01.03 | Met | [ci.yml](../../.github/workflows/ci.yml) — harden-runner, job permissions |
| OSPS-BR-03.01, 03.02 | Met | HTTPS; [release.yml](../../.github/workflows/release.yml) |
| OSPS-BR-07.01 | Met | gitleaks, `.gitleaks.toml` |
| OSPS-DO-01.01 | Met | README, DEVELOPMENT_GUIDE, ibexharness.com/docs |
| OSPS-DO-02.01 | Met | [CONTRIBUTING § Reporting defects](../../CONTRIBUTING.md#reporting-defects) |
| OSPS-GV-02.01, 03.01 | Met | Issues, CONTRIBUTING |
| OSPS-LE-02.01, 03.01 | Met | [LICENSE](../../LICENSE) |
| OSPS-LE-02.02, 03.02 | Met | MIT on [releases](https://github.com/Rick1330/ibex-harness/releases) |
| OSPS-QA-01.01, 01.02 | Met | Public GitHub repo |
| OSPS-QA-02.01 | Met | `go.mod`, `web/package.json`, `pnpm-lock.yaml` |
| OSPS-QA-04.01 | N/A | Single monorepo |
| OSPS-QA-05.01, 05.02 | Met | No binaries in VCS |
| OSPS-VM-02.01 | Met | `.github/SECURITY.md` |

### Level 2 (19 criteria) — highlights

| ID | Notes |
| --- | --- |
| OSPS-GV-01.01, 01.02 | [GOVERNANCE.md §1–2](./GOVERNANCE.md) |
| OSPS-LE-01.01 | DCO in CONTRIBUTING + CI |
| OSPS-SA-03.01 | GOVERNANCE §5, SECURITY.md |
| OSPS-VM-04.01 | GitHub Security Advisories |

### Level 3 (21 criteria) — known gaps

| ID | Status | Notes |
| --- | --- | --- |
| OSPS-AC-04.02 | Met | Per-job least privilege in [ci.yml](../../.github/workflows/ci.yml) |
| OSPS-BR-01.04 | Met | Pinned actions + harden-runner in CI |
| OSPS-BR-02.02, OSPS-QA-02.02 | Met | Tag-associated release assets + SBOM ([release.yml](../../.github/workflows/release.yml)) |
| OSPS-BR-07.02 | Met | Secrets policy in [SECURITY.md §6](./SECURITY.md#6-data-protection-encryption-secrets-key-management) |
| OSPS-DO-03.01, OSPS-DO-03.02 | Met | Cosign verify + OIDC identity in [RELEASING.md](./RELEASING.md#verify-release-integrity-and-authenticity) |
| OSPS-DO-04.01, OSPS-DO-05.01 | Met | Support/EOL in [RELEASING.md](./RELEASING.md#support-scope-and-security-updates-osps-do-0401-osps-do-0501) |
| OSPS-GV-04.01 | Met | [GOVERNANCE.md §3](./GOVERNANCE.md#3-permission-escalation-review-osps-gv-0401) |
| OSPS-QA-04.02 | N/A | Single monorepo |
| OSPS-QA-06.02, OSPS-QA-06.03 | Met | [CONTRIBUTING.md](../../CONTRIBUTING.md#required-ci-checks), [TESTING_STRATEGY.md](./TESTING_STRATEGY.md) |
| OSPS-QA-07.01 | **Unmet** | Solo mode: 0 required approvals ([ADR-0003](../content/docs/adr/0003-branch-protection-and-merge-policy.mdx)); CI gates still mandatory |
| OSPS-SA-03.02 | Met (documented) | Threat model [SECURITY.md §3](./SECURITY.md#3-threat-model-what-we-defend-against); formal workshop cadence Phase 5 |
| OSPS-VM-04.02 | **Unmet/defer** | No VEX feed yet — Phase 5 ([GOVERNANCE.md §6](./GOVERNANCE.md#6-vulnerability-disclosure-and-publication-osps-vm-0401)) |
| OSPS-VM-05.01–05.03, OSPS-VM-06.01–06.02 | Met | [DEPENDENCIES.md §9.0.1–9.0.2](./DEPENDENCIES.md#901-sca-remediation-thresholds-osps-vm-05010503) |

---

## Branch protection (Scorecard)

Apply or refresh after changing [`.github/branch-protection-main.json`](../../.github/branch-protection-main.json):

```bash
bash infra/scripts/apply-branch-protection.sh
```

Solo mode: **0 required approving reviews** per ADR-0003; PR + CI gates remain mandatory.

## Signed releases (Scorecard)

Tagged releases attach `sbom.spdx.json` + `sbom.spdx.json.sigstore` (cosign bundle). Verify with commands in [RELEASING.md](./RELEASING.md).

---

## Passing level (CII) — completed

The passing badge is **earned**. Maintainer-only form playbooks (outside git) may mirror the justifications below when filling bestpractices.dev.

### General project fields

| Field | Value |
| --- | --- |
| Description | Production-grade platform for AI agent memory, context assembly, and secure LLM proxying. |
| Languages | `Go, TypeScript` (Python services planned; manifests added when shipped) |
| License | `MIT` |
| Project URL | [ibexharness.com](https://ibexharness.com) |
| Repo URL | [github.com/Rick1330/ibex-harness](https://github.com/Rick1330/ibex-harness) |

### Intentional Unmet (Passing)

| Criterion | Status | Justification |
| --- | --- | --- |
| `enhancement_responses` | Unmet | Pre-1.0 solo project; enhancements are tracked via pull requests and the public roadmap instead of a public enhancement-request tracker. |
