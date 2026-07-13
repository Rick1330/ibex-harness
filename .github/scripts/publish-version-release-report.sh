#!/usr/bin/env bash
# Publish a structured GitHub Actions job summary for the Version Release PR workflow.
# Usage: publish-version-release-report.sh <step_outcome> <prs_created> <pr_number> <releases_created> <release_tag>
set -euo pipefail

step_outcome="${1:-unknown}"
prs_created="${2:-false}"
pr_number="${3:-}"
releases_created="${4:-false}"
release_tag="${5:-}"
repo="${GITHUB_REPOSITORY:-unknown/unknown}"
server="${GITHUB_SERVER_URL:-https://github.com}"

{
  echo "## Version Release PR workflow"
  echo ""
  echo "| Field | Value |"
  echo "| --- | --- |"
  echo "| Propose step | \`${step_outcome}\` |"
  echo "| PR created/updated | \`${prs_created}\` |"
  if [[ -n "$pr_number" ]]; then
    echo "| Release PR | [#${pr_number}](${server}/${repo}/pull/${pr_number}) |"
  else
    echo "| Release PR | _none_ |"
  fi
  echo "| Release tagged | \`${releases_created}\` |"
  if [[ -n "$release_tag" ]]; then
    echo "| Tag | \`${release_tag}\` |"
  fi
  echo ""
} >>"$GITHUB_STEP_SUMMARY"

if [[ "$step_outcome" != "success" ]]; then
  {
    echo "### Action required"
    echo ""
    echo "The version release engine step did not succeed. Check the step logs above for auth, permissions, or conventional-commit errors."
    echo ""
    echo "See [RELEASING.md](${server}/${repo}/blob/main/web/engineering/RELEASING.md) for workflow permissions and token setup."
  } >>"$GITHUB_STEP_SUMMARY"
  echo "::error::Version release engine step failed (outcome=${step_outcome})"
  exit 1
fi

if [[ "$prs_created" == "true" && -n "$pr_number" ]]; then
  echo "::notice title=Version release PR updated::PR #${pr_number} is ready for review"
  exit 0
fi

if [[ "$releases_created" == "true" ]]; then
  echo "::notice title=Version release tagged::Release ${release_tag:-tag} published from merged release PR"
  exit 0
fi

{
  echo "### No release PR opened"
  echo ""
  echo "The workflow completed successfully but did not open or update a release PR."
  echo "This is normal when there are no releasable conventional commits since the last release baseline."
} >>"$GITHUB_STEP_SUMMARY"
echo "::notice title=Version release idle::No release PR was required on this run"
exit 0
