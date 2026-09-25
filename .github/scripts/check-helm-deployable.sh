#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CHART="${ROOT}/infra/helm/ibex-harness"
OVERLAY_INPUT="${1:?usage: check-helm-deployable.sh <staging-or-production-values.yaml>}"

case "${OVERLAY_INPUT}" in
  values-staging.yaml|values-prod.yaml)
    OVERLAY_INPUT="${CHART}/${OVERLAY_INPUT}"
    ;;
esac

if ! OVERLAY="$(realpath -e -- "${OVERLAY_INPUT}")"; then
  echo "refusing missing overlay: ${OVERLAY_INPUT}" >&2
  exit 2
fi
case "${OVERLAY}" in
  "${CHART}/values-staging.yaml"|"${CHART}/values-prod.yaml") ;;
  *) echo "refusing overlay outside checked-in staging/production allowlist: ${OVERLAY_INPUT}" >&2; exit 2 ;;
esac

command -v helm >/dev/null 2>&1 || { echo "helm is required" >&2; exit 1; }
command -v awk >/dev/null 2>&1 || { echo "awk is required" >&2; exit 1; }

rendered="$(helm template ibex "${CHART}" -f "${OVERLAY}")"
count=0
while IFS= read -r image; do
  [[ -n "${image}" ]] || continue
  count=$((count + 1))
  if [[ ! "${image}" =~ @sha256:([a-f0-9]{64})$ ]]; then
    echo "image is not digest-pinned: ${image}" >&2
    exit 1
  fi
  digest="${BASH_REMATCH[1]}"
  printf -v repeated '%*s' 64 ''
  repeated="${repeated// /${digest:0:1}}"
  if [[ "${digest}" == "${repeated}" ]]; then
    echo "image has a sentinel repeated-character digest: ${image}" >&2
    exit 1
  fi
done < <(awk '/^[[:space:]]*image:[[:space:]]*/ { sub(/^[[:space:]]*image:[[:space:]]*/, ""); gsub(/^\"|\"$/, ""); print }' <<<"${rendered}")

if (( count == 0 )); then
  echo "rendered overlay contains no image fields" >&2
  exit 1
fi

echo "Deployable Helm overlay verified (${count} rendered images): ${OVERLAY}"
