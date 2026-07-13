# Releasing IBEX Harness

This repository uses an **automated version release pipeline** to keep releases consistent and auditable. The pipeline opens a **Version Release PR** on each push to `main` (workflow: `.github/workflows/version-release-pr.yml`).

## Source of truth

- **Releases are created by the pipeline**, not manually in the GitHub UI.
- Version tags follow **Semantic Versioning**: `vMAJOR.MINOR.PATCH`.
- The canonical changelog lives at **`CHANGELOG.md`** (repository root) and must be updated as part of a release PR.

## Normal release flow

1. Merge changes to `main` using Conventional Commits.
2. The **Version Release PR** workflow opens or updates a release PR (`chore(release): prepare vX.Y.Z`).
3. Review the release PR:
   - Ensure `CHANGELOG.md` is correct and operationally useful.
4. Merge the release PR.
5. The pipeline creates a tag like `vX.Y.Z`, which triggers:
   - `release.yml` (GitHub Release + SBOM + cosign signature)
   - `docker-publish.yml` via the `release.yml` reusable call.

Release assets include `sbom.spdx.json`, `sbom.spdx.json.sig`, and `sbom.spdx.json.pem` for OpenSSF Scorecard signed-release visibility. See [OPENSSF_BEST_PRACTICES.md](./OPENSSF_BEST_PRACTICES.md).

## Workflow permissions

If the Version Release PR workflow cannot open PRs, enable **Settings → Actions → General → Workflow permissions → Allow GitHub Actions to create and approve pull requests**, or add a `VERSION_RELEASE_TOKEN` secret (`contents` + `pull-requests` scope). The legacy `RELEASE_PLEASE_TOKEN` secret name is also accepted during transition.

## Hotfix releases

Hotfixes use the same flow: merge a `fix/*` branch to `main` quickly; the pipeline proposes the next patch release.

## Configuration files

| File | Purpose |
| --- | --- |
| `version-release.config.json` | Changelog path, semver tags, PR title pattern |
| `.version-release-manifest.json` | Current released version (managed by the pipeline) |
