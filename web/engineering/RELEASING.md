# Releasing IBEX Harness

This repository uses an **automated version release pipeline** to keep releases consistent and auditable. Workflow: `.github/workflows/version-release-pr.yml`.

## Which workflows are which (read this first)

These names look similar but do **different** jobs. You usually need only one at a time.

| Workflow (Actions name) | File | What it does | When it runs | Do you need it? |
| --- | --- | --- | --- | --- |
| **Version Release PR** | `version-release-pr.yml` | Opens/updates the weekly `chore(release): prepare vX.Y.Z` PR; on merge **publish**, creates the git tag + GitHub Release notes | Sunday 08:00 UTC propose; publish on `chore(release): prepare v…` merge | **Yes** for cutting semver releases |
| **Tagged Release** | `release.yml` | Builds SBOM, signs with cosign, **uploads** `sbom.spdx.json` + `.sigstore` onto an **existing** GitHub Release | Tag push `v*.*.*`, release published, or manual `workflow_dispatch` with `tag_name` | **Yes** for Scorecard signed-release assets. Input must be an **existing** tag (today: `v0.1.0`) |
| **Tagged Release Docker** | `release-docker.yml` | Publishes **version-tagged** container images (`ghcr.io/.../auth:vX.Y.Z`) | Only on **tag push** `v*.*.*` | Automatic with new tags; not used for manual SBOM repair |
| **Docker Publish** | `docker-publish.yml` | Builds/scans/pushes **`latest`** (and related) images after successful CI on `main` | `workflow_run` after CI, PRs (scan-only), manual, or called by Tagged Release Docker | **Unrelated to SBOM/releases.** A green Docker Publish does **not** attach release assets |

**Confusion trap:** After a merge, **Docker Publish** often succeeds with `latest` images. That is **not** Tagged Release. To attach SBOM signatures to `v0.1.0`, run **Actions → Tagged Release → Run workflow** with `tag_name=v0.1.0`.

## Release cadence

| When | What happens |
| --- | --- |
| **Every Sunday 08:00 UTC** (cron) | Opens or updates a **Version Release PR** with the week's conventional commits. Does **not** run on every merge to `main`. |
| **You merge the release PR** | Push to `main` triggers **publish** mode: creates `vX.Y.Z` tag and GitHub Release. |
| **`workflow_dispatch` → propose** | Manually refresh the release PR between Sundays if needed. |
| **`workflow_dispatch` → publish** | Manually create the tag after merging a release PR (if the automatic publish step did not run). |
| **Tagged Release** | On tag push / manual, attaches SBOM + cosign assets (`release.yml`). Versioned images use `release-docker.yml` on tag push only. |

Normal feature and fix PRs merge to `main` **without** opening a release PR each time.

## Versioning standard

IBEX Harness is currently in **pre-1.0** maturity. We use Semantic Versioning with these rules:

- `v0.x.y` while APIs and architecture are still evolving.
- `v1.0.0` only after explicit production-readiness and compatibility sign-off.
- During pre-1.0:
  - New features typically bump **minor** (`0.x+1.0`).
  - Fixes without feature/API changes bump **patch** (`0.x.y+1`).

Configured in `version-release.config.json` and `.version-release-manifest.json`.

## Source of truth

- **Releases are created by the pipeline**, not manually in the GitHub UI.
- Version tags follow **Semantic Versioning**: `vMAJOR.MINOR.PATCH`.
- The canonical changelog lives at **`CHANGELOG.md`** (repository root) and is updated as part of a release PR.
- The public changelog at [ibexharness.com/releases](https://ibexharness.com/releases) is generated from root `CHANGELOG.md` at web build time. The site shows **curated highlights** per release (scoped badges, issue links, collapsible full lists). The complete machine-readable history remains on GitHub Releases and in `CHANGELOG.md`.

## Normal release flow

1. Merge changes to `main` using Conventional Commits throughout the week.
2. **Sunday (or manual propose):** the pipeline opens/updates `chore(release): prepare vX.Y.Z`.
3. Review the release PR — confirm `CHANGELOG.md` and semver.
4. Merge the release PR (squash).
5. **Publish** runs on the `chore(release): prepare v…` merge commit → tag `vX.Y.Z` → `release.yml` (SBOM + cosign bundle) + `release-docker.yml` (versioned images on tag push). Separately, **Docker Publish** may still push `latest` after ordinary CI on `main` — that is expected and independent.

If a tag was created while `release.yml` was broken, re-attach assets with **Actions → Tagged Release → Run workflow** and `tag_name=vX.Y.Z` (must already exist; no need to recreate the tag).

## Automation branch and labels

The **version release engine** opens PRs from an internal automation branch named **`release--branches--main`**. Do not use this branch for feature work. If the engine recreates its legacy default branch name, the Version Release workflow renames it to `release--branches--main` automatically after each propose run.

Release PRs are labeled `version-release: pending` until merge, then `version-release: tagged`. PR titles follow `chore(release): prepare vX.Y.Z`.

Because release PRs are created by `github-actions[bot]`, the standalone **Semantic PR Title** workflow does not run on them. The Version Release workflow posts the required `semantic-pr-title` check on the release PR head commit.

**CodeScene** is advisory only (not a merge gate).

## Workflow permissions

If the Version Release PR workflow cannot open PRs, enable **Settings → Actions → General → Workflow permissions → Read and write permissions** and **Allow GitHub Actions to create and approve pull requests**, or add a `VERSION_RELEASE_TOKEN` secret (`contents` + `pull-requests` scope).

## Hotfix releases

For urgent patches: merge the fix to `main`, then either wait for the next Sunday propose run or run **Version Release PR** manually with mode **propose**, review, and merge the release PR.

## Configuration files

| File | Purpose |
| --- | --- |
| `version-release.config.json` | Versioning policy, changelog path, semver tags, PR title pattern |
| `.version-release-manifest.json` | Current released version baseline (managed by the pipeline) |

## Verify release integrity and authenticity

After downloading release assets from [GitHub Releases](https://github.com/Rick1330/ibex-harness/releases):

### Integrity (OSPS-DO-03.01)

1. Download `sbom.spdx.json` and `sbom.spdx.json.sigstore` for tag `vX.Y.Z`.
2. Install [cosign](https://docs.sigstore.dev/cosign/system_install/) (v2+).
3. Verify the signature bundle:

```bash
# Tag push / tag-associated signing (replace TAG, e.g. v0.1.0)
cosign verify-blob \
  --bundle sbom.spdx.json.sigstore \
  --certificate-oidc-issuer-regexp='https://token\.actions\.githubusercontent\.com' \
  --certificate-identity-regexp="https://github\.com/Rick1330/ibex-harness/\.github/workflows/release\.yml@refs/tags/${TAG}" \
  sbom.spdx.json

# Documented repair only: workflow_dispatch of release.yml from main
# (use only when re-attaching assets to an existing tag)
cosign verify-blob \
  --bundle sbom.spdx.json.sigstore \
  --certificate-oidc-issuer-regexp='https://token\.actions\.githubusercontent\.com' \
  --certificate-identity-regexp='https://github\.com/Rick1330/ibex-harness/\.github/workflows/release\.yml@refs/heads/main' \
  sbom.spdx.json
```

Signatures from other workflows or refs must not match. Replace `TAG` with the release tag under verification.

4. Optionally compare the file SHA-256 with the digest listed in the GitHub Release asset metadata.

Container images published to GHCR include GitHub artifact attestations (see `docker-publish.yml` / `release-docker.yml`).

### Release author / process (OSPS-DO-03.02)

- Tags `v*.*.*` are created only by the **Version Release PR** publish step or documented hotfix flow — not ad hoc in the GitHub UI.
- SBOM signing runs in [`.github/workflows/release.yml`](../../.github/workflows/release.yml) using GitHub OIDC (`id-token: write`); cosign certificates identify the workflow and repository.
- Branch protection on `main` blocks unreviewed direct pushes ([`.github/branch-protection-main.json`](../../.github/branch-protection-main.json)).

## Support scope and security updates (OSPS-DO-04.01, OSPS-DO-05.01)

**Pre-1.0 policy (current):**

| Release line | Support |
| --- | --- |
| Latest minor on `main` (e.g. `v0.1.x`) | Active development; security fixes land on `main` and ship in the next patch release |
| Previous minors (e.g. `v0.0.x`) | No guaranteed security backports after the next minor ships |
| Pre-release tags | Unsupported |

**Security update end-of-life:** When `v0.(n+1).0` is published, `v0.n.*` receives **no further security patches** unless explicitly announced in a GitHub Security Advisory.

After **v1.0.0**, this section will be updated to a documented LTS window (minimum 12 months security support for the latest major).

## License on releases

Project-authored source for each tag remains under the repository [MIT LICENSE](../../LICENSE). That statement does **not** relicense third-party components listed in release SBOMs, nor the contents of container images: those materials remain under their own licenses. Use `sbom.spdx.json` (and image metadata) for third-party license notices and package identity.
