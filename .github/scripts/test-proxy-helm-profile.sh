#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CHART="${ROOT}/infra/helm/ibex-harness"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

command -v helm >/dev/null 2>&1 || {
  echo "helm is required for Proxy profile chart tests" >&2
  exit 1
}

helm lint "$CHART"
helm lint "$CHART" -f "${CHART}/values-staging.yaml"
helm lint "$CHART" -f "${CHART}/values-prod.yaml"

helm template ibex "$CHART" > "${TMP_DIR}/development.yaml"
helm template ibex "$CHART" -f "${CHART}/values-staging.yaml" > "${TMP_DIR}/staging.yaml"
helm template ibex "$CHART" -f "${CHART}/values-prod.yaml" > "${TMP_DIR}/production.yaml"

assert_contains() {
  local file="$1" expected="$2" label="$3"
  if ! grep -Fq -- "$expected" "$file"; then
    printf 'FAIL: %s: rendered manifest is missing %s\n' "$label" "$expected" >&2
    exit 1
  fi
  printf 'PASS: %s\n' "$label"
}

assert_contains "${TMP_DIR}/development.yaml" 'value: "development"' 'local chart explicitly selects development'
assert_contains "${TMP_DIR}/development.yaml" 'name: "ibex-redis"' 'local chart names its optional Redis Secret'
assert_contains "${TMP_DIR}/development.yaml" 'optional: true' 'local development may omit Redis Secret'
assert_contains "${TMP_DIR}/staging.yaml" 'value: "staging"' 'staging overlay explicitly selects staging'
assert_contains "${TMP_DIR}/staging.yaml" 'name: "ibex-redis"' 'staging references the documented Redis Secret'
assert_contains "${TMP_DIR}/staging.yaml" 'key: "redis-url"' 'staging references the documented Redis Secret key'
assert_contains "${TMP_DIR}/staging.yaml" 'optional: false' 'staging requires its Redis Secret'
assert_contains "${TMP_DIR}/production.yaml" 'value: "production"' 'production overlay explicitly selects production'
assert_contains "${TMP_DIR}/production.yaml" 'name: "ibex-redis"' 'production references the documented Redis Secret'
assert_contains "${TMP_DIR}/production.yaml" 'key: "redis-url"' 'production references the documented Redis Secret key'
assert_contains "${TMP_DIR}/production.yaml" 'optional: false' 'production requires its Redis Secret'
assert_contains "${TMP_DIR}/production.yaml" 'value: "live"' 'production explicitly selects live LLM mode'
assert_contains "${TMP_DIR}/production.yaml" 'name: "ibex-proxy-provider"' 'production references the provider Secret'
assert_contains "${TMP_DIR}/production.yaml" 'key: "openai-api-key"' 'production references the provider Secret key'

if helm template ibex "$CHART" -f "${CHART}/values-prod.yaml" --set proxy.environment=development >/dev/null 2>&1; then
	echo 'FAIL: production overlay accepted a development Proxy profile override' >&2
	exit 1
fi
if helm template ibex "$CHART" -f "${CHART}/values-prod.yaml" --set proxy.environment=development --skip-schema-validation >/dev/null 2>&1; then
	echo 'FAIL: production template guard accepted a development Proxy profile override' >&2
	exit 1
fi

for overlay in values-staging.yaml values-prod.yaml; do
	if output="$(bash "${ROOT}/.github/scripts/check-helm-deployable.sh" "${CHART}/${overlay}" 2>&1)"; then
		printf 'FAIL: non-deployable sentinel digests unexpectedly passed %s\n' "$overlay" >&2
		exit 1
	fi
	grep -Fq 'sentinel repeated-character digest' <<<"$output" || {
		printf 'FAIL: %s rejected for an unexpected reason: %s\n' "$overlay" "$output" >&2
		exit 1
		}
done

cp "${CHART}/values-prod.yaml" "${TMP_DIR}/values-prod.yaml"
if output="$(bash "${ROOT}/.github/scripts/check-helm-deployable.sh" "${TMP_DIR}/values-prod.yaml" 2>&1)"; then
	echo 'FAIL: external values-prod.yaml was accepted by the deploy preflight' >&2
	exit 1
fi
grep -Fq 'outside checked-in staging/production allowlist' <<<"$output" || {
	printf 'FAIL: external overlay rejected for an unexpected reason: %s\n' "$output" >&2
	exit 1
}

for bad_profile in '' developmentish; do
  if helm template ibex "$CHART" --set-string "proxy.environment=${bad_profile}" >/dev/null 2>&1; then
    printf 'FAIL: invalid Proxy profile %q unexpectedly rendered\n' "$bad_profile" >&2
    exit 1
  fi
done

if helm template ibex "$CHART" --set proxy.environment=null >/dev/null 2>&1; then
  echo 'FAIL: missing Proxy profile unexpectedly rendered' >&2
  exit 1
fi

echo 'Proxy Helm profile and Redis Secret regression cases passed.'
