# Releasing IBEX Harness

This repository uses an **automated version release pipeline** to keep releases consistent and auditable. The pipeline opens a **Version Release PR** on each push to `main` (workflow: `.github/workflows/version-release-pr.yml`).

## Versioning standard

IBEX Harness is currently in **pre-1.0** maturity. We use Semantic Versioning with these rules:

- `v0.x.y` while APIs and architecture are still evolving.
- `v1.0.0` only after explicit production-readiness and compatibility sign-off.
- During pre-1.0:
  - New features typically bump **minor** (`0.x+1.0`).
  - Fixes without feature/API changes bump **patch** (`0.x.y+1`).

The release pipeline is configured for this policy in `version-release.config.json` and `.version-release-manifest.json`.

## Source of truth

- **Releases are created by the pipeline**, not manually in the GitHub UI.
- Version tags follow **Semantic Versioning**: `vMAJOR.MINOR.PATCH`.
- The canonical changelog lives at **`CHANGELOG.md`** (repository root) and must be updated as part of a release PR.

## Normal release flow

1. Merge changes to `main` using Conventional Commits.
2. The **Version Release PR** workflow opens or updates a release PR (`chore(release): prepare vX.Y.Z`).
3. Review the release PR:
   - Ensure `CHANGELOG.md` is correct and operationally useful.
   - Confirm the proposed version matches pre-1.0 policy (`v0.x.y`).
4. Merge the release PR.
5. The pipeline creates a tag like `vX.Y.Z`, which triggers:
   - `release.yml` (GitHub Release + SBOM + cosign signature)
   - `docker-publish.yml` via the `release.yml` reusable call.

Release assets include `sbom.spdx.json`, `sbom.spdx.json.sig`, and `sbom.spdx.json.pem` for OpenSSF Scorecard signed-release visibility. See [OPENSSF_BEST_PRACTICES.md](./OPENSSF_BEST_PRACTICES.md).

## Automation branch and labels

The version release engine opens PRs from an internal branch named `release-please--branches--main`. That name is imposed by the upstream engine and is **not** user-facing branding — do not use it for feature work. Release PRs are labeled `version-release: pending` until merge, then `version-release: tagged`.

## When the workflow runs

| Trigger | Behavior |
| --- | --- |
| Push to `main` | Opens or updates the Version Release PR when there are releasable conventional commits. **Skipped** when the push is a merged release PR (`chore(release): prepare v…` squash commit) to avoid a release loop. |
| `workflow_dispatch` | Manual run from **Actions → Version Release PR** when you want to refresh the release PR on demand. |

Because release PRs are created by `github-actions[bot]`, the standalone **Semantic PR Title** workflow does not run on them (GitHub Actions token chaining). The Version Release workflow posts the required `semantic-pr-title` check directly on the release PR head commit.

**CodeScene** is advisory only (not a merge gate). If it stays queued, merge once required CI gates are green.

## Workflow permissions

If the Version Release PR workflow cannot open PRs, enable **Settings → Actions → General → Workflow permissions → Read and write permissions** and **Allow GitHub Actions to create and approve pull requests**, or add a `VERSION_RELEASE_TOKEN` secret (`contents` + `pull-requests` scope).

## Hotfix releases

Hotfixes use the same flow: merge a `fix/*` branch to `main` quickly; the pipeline proposes the next patch release.

## Configuration files

| File | Purpose |
| --- | --- |
| `version-release.config.json` | Versioning policy, changelog path, semver tags, PR title pattern |
| `.version-release-manifest.json` | Current released version baseline (managed by the pipeline) |
