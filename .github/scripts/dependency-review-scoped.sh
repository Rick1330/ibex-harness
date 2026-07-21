#!/usr/bin/env bash
# Dependency review with manifest-scoped GHSA exceptions (not global allow-ghsas).
set -euo pipefail

allowlist_file="$(cd "$(dirname "$0")/../dependency-review" && pwd)/licenses-tools-allowlist.conf"
# shellcheck source=/dev/null
source "$allowlist_file"

repo="${GITHUB_REPOSITORY:?}"
base_sha="${GITHUB_EVENT_PULL_REQUEST_BASE_SHA:-}"
head_sha="${GITHUB_SHA:?}"

if [[ -z "$base_sha" ]]; then
  echo "dependency-review-scoped: missing PR base SHA; skipping" >&2
  exit 0
fi

basehead="${base_sha}...${head_sha}"
compare_json="$(gh api "repos/${repo}/dependency-graph/compare/${basehead}")"

is_allowed_ghsa() {
  local ghsa="$1"
  local entry
  IFS=',' read -ra allowed <<< "$ALLOWED_GHSAS"
  for entry in "${allowed[@]}"; do
    if [[ "$entry" == "$ghsa" ]]; then
      return 0
    fi
  done
  return 1
}

normalize_version() {
  local ver="${1#v}"
  echo "$ver"
}

allowed_version="$(normalize_version "$ALLOWED_VERSION")"
failures=0

while IFS= read -r dep; do
  [[ -z "$dep" ]] && continue
  [[ "$(jq -r '.change_type' <<< "$dep")" == "added" ]] || continue
  manifest="$(jq -r '.manifest' <<< "$dep")"
  package="$(jq -r '.name' <<< "$dep")"
  version="$(normalize_version "$(jq -r '.version' <<< "$dep")")"
  vuln_count="$(jq '.vulnerabilities | length' <<< "$dep")"
  [[ "$vuln_count" -eq 0 ]] && continue

  while IFS= read -r vuln; do
    [[ -z "$vuln" ]] && continue
    ghsa="$(jq -r '.advisory_ghsa_id' <<< "$vuln")"
    severity="$(jq -r '.severity' <<< "$vuln")"

    if [[ "$manifest" == "$LICENSES_MANIFEST" ]] \
      && [[ "$package" == "$ALLOWED_PACKAGE" ]] \
      && [[ "$version" == "$allowed_version" ]] \
      && is_allowed_ghsa "$ghsa"; then
      echo "allowed (licenses CI tools): ${package}@${version} ${ghsa} in ${manifest}"
      continue
    fi

    echo "dependency review blocked: ${package}@${version} ${ghsa} (${severity}) in ${manifest}" >&2
    failures=$((failures + 1))
  done < <(jq -c '.vulnerabilities[]' <<< "$dep")
done < <(jq -c '.[]' <<< "$compare_json")

if [[ "$failures" -gt 0 ]]; then
  echo "" >&2
  echo "${failures} vulnerable dependency change(s) outside the scoped licenses-tools allowlist." >&2
  echo "Production manifests must have zero vulnerabilities." >&2
  echo "Only ${ALLOWED_PACKAGE}@${ALLOWED_VERSION} in ${LICENSES_MANIFEST} may use the allowlisted GHSAs." >&2
  exit 1
fi

echo "dependency-review-scoped: no blocking vulnerabilities"
