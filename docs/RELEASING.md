# Releasing IBEX Harness

This repository uses **Release Please** to keep releases consistent and auditable.

## Source of truth

- **Releases are created by the pipeline**, not manually in the GitHub UI.
- Version tags follow **Semantic Versioning**: `vMAJOR.MINOR.PATCH`.
- The canonical changelog lives at `docs/CHANGELOG.md` and must be updated as part of a release PR.

## Normal release flow

1. Merge changes to `main` using Conventional Commits.
2. The **Release Please** workflow opens or updates a Release PR.
3. Review the Release PR:
   - Ensure `docs/CHANGELOG.md` is correct and operationally useful.
4. Merge the Release PR.
5. Release Please creates a tag like `vX.Y.Z`, which triggers:
   - `release.yml` (GitHub Release + SBOM)
   - `docker-publish.yml` via the `release.yml` reusable call.

## Hotfix releases

Hotfixes are the same flow, but you should use `fix/*` branches and merge to `main` quickly. Release Please will propose the next patch release.
