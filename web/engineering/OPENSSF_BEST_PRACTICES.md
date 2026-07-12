# OpenSSF Best Practices (CII) — enrollment and evidence map

OpenSSF Scorecard’s [CII-Best-Practices check](https://github.com/ossf/scorecard/blob/main/docs/checks.md#cii-best-practices) reads the [OpenSSF Best Practices badge](https://www.bestpractices.dev/) API. Enrolling the project raises that Scorecard signal (in-progress → passing → silver → gold).

## Maintainer enrollment (one-time)

1. Open [Create a new best practices project](https://www.bestpractices.dev/projects/new).
2. Set **Project URL** to `https://github.com/Rick1330/ibex-harness`.
3. Complete criteria using the evidence map below (link to workflows, ADRs, and docs).
4. After the project is created, add the badge to `README.md`:

   ```markdown
   [![OpenSSF Best Practices](https://www.bestpractices.dev/projects/<PROJECT_ID>/badge)](https://www.bestpractices.dev/projects/<PROJECT_ID>)
   ```

5. Re-run the [Scorecard workflow](https://github.com/Rick1330/ibex-harness/actions/workflows/scorecard.yml) (push to `main` or wait for the weekly schedule).

## Evidence map (repo artifacts)

| Best practices theme | IBEX Harness evidence |
| --- | --- |
| Public version control | GitHub repo; Conventional Commits ([CONTRIBUTING.md](../../CONTRIBUTING.md)) |
| Build & test in CI | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) — area gates, unit/integration coverage |
| Vulnerability reporting | [`.github/SECURITY.md`](../../.github/SECURITY.md), security issue template |
| No unfixed critical vulns (process) | Trivy/OSV/govulncheck in CI; Dependabot ([`.github/dependabot.yml`](../../.github/dependabot.yml)) |
| Static analysis | CodeQL, Semgrep, golangci-lint ([ADR-0008](../content/docs/adr/0008-security-ci-gates.mdx)) |
| SBOM / dependency visibility | [`.github/workflows/sbom.yml`](../../.github/workflows/sbom.yml) (Syft + Grype) |
| Signed release artifacts | [`.github/workflows/release.yml`](../../.github/workflows/release.yml) — cosign `*.sig` on SBOM |
| Branch protection | [`.github/branch-protection-main.json`](../../.github/branch-protection-main.json); apply via `infra/scripts/apply-branch-protection.sh` |
| Security policy documented | [SECURITY.md](./SECURITY.md), [ADR-0008](../content/docs/adr/0008-security-ci-gates.mdx) |

## Branch protection (Scorecard)

Scorecard’s [Branch-Protection check](https://github.com/ossf/scorecard/blob/main/docs/checks.md#branch-protection) expects `main` to require PRs, block force-push, enforce status checks, and (with an admin token) settings such as `enforce_admins` and up-to-date branches.

Apply or refresh settings after changing [`.github/branch-protection-main.json`](../../.github/branch-protection-main.json):

```bash
bash infra/scripts/apply-branch-protection.sh
```

Solo mode keeps **0 required approving reviews** per [ADR-0003](../content/docs/adr/0003-branch-protection-and-merge-policy.mdx); PR + CI gates remain mandatory.

## Signed releases (Scorecard)

The [Signed-Releases check](https://github.com/ossf/scorecard/blob/main/docs/checks.md#signed-releases) inspects the last releases for signature files (`*.sig`, `*.sigstore`, `*.intoto.jsonl`, etc.). Tagged releases (`v*.*.*`) attach a cosign signature for `sbom.spdx.json` (see `release.yml`). Container images use GitHub attestations in `docker-publish.yml`.

After the first semver tag from Release Please, confirm release assets include `sbom.spdx.json.sig`.
