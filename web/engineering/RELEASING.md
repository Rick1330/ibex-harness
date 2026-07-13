# Releasing IBEX Harness

This repository uses an **automated version release pipeline** to keep releases consistent and auditable. Workflow: `.github/workflows/version-release-pr.yml`.

## Release cadence

| When | What happens |
| --- | --- |
| **Every Sunday 08:00 UTC** (cron) | Opens or updates a **Version Release PR** with the week's conventional commits. Does **not** run on every merge to `main`. |
| **You merge the release PR** | Push to `main` triggers **publish** mode: creates `vX.Y.Z` tag and GitHub Release. |
| **`workflow_dispatch` → propose** | Manually refresh the release PR between Sundays if needed. |
| **`workflow_dispatch` → publish** | Manually create the tag after merging a release PR (if the automatic publish step did not run). |
| **Tagged Release workflow** | On tag publish / `workflow_dispatch`, attaches SBOM + cosign assets (`release.yml`). |

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
- The public changelog at [ibexharness.com/releases](https://ibexharness.com/releases) is generated from root `CHANGELOG.md` at web build time.

## Normal release flow

1. Merge changes to `main` using Conventional Commits throughout the week.
2. **Sunday (or manual propose):** the pipeline opens/updates `chore(release): prepare vX.Y.Z`.
3. Review the release PR — confirm `CHANGELOG.md` and semver.
4. Merge the release PR (squash).
5. **Publish** runs on the `chore(release): prepare v…` merge commit → tag `vX.Y.Z` → `release.yml` (SBOM + cosign) + docker publish on tag push.

## Automation branch and labels

The version release engine opens PRs from an internal branch named `release-please--branches--main`. That name is imposed by the upstream engine — do not use it for feature work. Release PRs are labeled `version-release: pending` until merge, then `version-release: tagged`.

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
