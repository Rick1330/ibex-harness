#!/usr/bin/env bash
# Dependency review with manifest-scoped GHSA exceptions (not global allow-ghsas).
# Each exception applies only to one package pinned at one version in one
# manifest; entries must carry a documented reason in the conf file and be
# re-audited when the pinned dependency chain changes.
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

normalize_version() {
  local ver="${1#v}"
  echo "$ver"
}

# is_allowed "$manifest" "$package" "$version" "$ghsa"
is_allowed() {
  local manifest="$1" package="$2" version="$3" ghsa="$4"
  local entry entry_manifest entry_package entry_version entry_ghsas
  for entry in "${SCOPED_EXCEPTIONS[@]}"; do
    IFS='|' read -r entry_manifest entry_package entry_version entry_ghsas <<< "$entry"
    if [[ "$manifest" == "$entry_manifest" ]] \
      && [[ "$package" == "$entry_package" ]] \
      && [[ "$version" == "$(normalize_version "$entry_version")" ]] \
      && [[ ",${entry_ghsas}," == *",${ghsa},"* ]]; then
      return 0
    fi
  done
  return 1
}

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

    if is_allowed "$manifest" "$package" "$version" "$ghsa"; then
      echo "allowed (scoped exception): ${package}@${version} ${ghsa} in ${manifest}"
      continue
    fi

    echo "dependency review blocked: ${package}@${version} ${ghsa} (${severity}) in ${manifest}" >&2
    failures=$((failures + 1))
  done < <(jq -c '.vulnerabilities[]' <<< "$dep")
done < <(jq -c '.[]' <<< "$compare_json")

if [[ "$failures" -gt 0 ]]; then
  echo "" >&2
  echo "${failures} vulnerable dependency change(s) outside the scoped allowlist." >&2
  echo "Production manifests must have zero vulnerabilities." >&2
  echo "See .github/dependency-review/licenses-tools-allowlist.conf for the pinned exceptions." >&2
  exit 1
fi

echo "dependency-review-scoped: no blocking vulnerabilities"
