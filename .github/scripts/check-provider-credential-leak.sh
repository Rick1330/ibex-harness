#!/usr/bin/env bash
# Fail if provider credential sealed fields or plaintext keys leak into
# Management API surfaces, authclient response codecs, or credential-path logs.
#
# Scope (reviewed, milestone 4.A.5): static grep over declared modules below.
# Full OpenAPI export + runtime OTel attribute scanning: see issue #802.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

SEALED_PATTERNS=(
  'encrypted_api_key'
  'ciphertext'
  'wrapped_dek'
)

fail=0

scan_sealed() {
  local label="$1"
  shift
  local pat
  for pat in "${SEALED_PATTERNS[@]}"; do
    if rg -n --glob '!**/tests/**' --glob '!**/*_test.go' --glob '!**/test_*.py' \
      "${pat}" "$@" 2>/dev/null; then
      echo "provider credential leak pattern (${label}): ${pat}" >&2
      fail=1
    fi
  done
}

# Management API HTTP surface (responses / routers / orchestration).
scan_sealed "api-surface" \
  "${ROOT}/services/api/app/schemas/providers.py" \
  "${ROOT}/services/api/app/routers/providers.py" \
  "${ROOT}/services/api/app/services/providers.py"

# authclient: sealed column names must never appear in codecs/client modules.
# (Wire Get may carry api_key plaintext for Auth↔proxy; sealed blobs must not.)
if [[ -d "${ROOT}/packages/authclient/src/authclient" ]]; then
  scan_sealed "authclient" \
    "${ROOT}/packages/authclient/src/authclient/provider_credentials.py" \
    "${ROOT}/packages/authclient/src/authclient/provider_credential_codec.py" \
    "${ROOT}/packages/authclient/src/authclient/codec.py"
fi

# Auth gRPC credential handlers + service: no sealed-column identifiers in
# externally-facing handler files (persistence stays in repository/).
scan_sealed "auth-handlers" \
  "${ROOT}/services/auth/internal/grpc/provider_credentials.go" \
  "${ROOT}/services/auth/internal/service/provider_credentials.go"

# Response models must not declare api_key (write request may).
if rg -n 'api_key' "${ROOT}/services/api/app/schemas/providers.py" \
  | rg -v 'UpsertRequest|ApiKeyStr|api_key: ApiKeyStr'; then
  echo "unexpected api_key field outside upsert request schema" >&2
  fail=1
fi

# Structured-log field keys must not name secrets on credential paths.
# Matches logger-style key args: "api_key", "ciphertext", "wrapped_dek".
LOG_KEY_RE='"(api_key|ciphertext|wrapped_dek|encrypted_api_key)"[[:space:]]*,'
log_targets=(
  "${ROOT}/services/api/app/routers/providers.py"
  "${ROOT}/services/api/app/services/providers.py"
  "${ROOT}/services/api/app/services/provider_validate.py"
  "${ROOT}/services/api/app/services/provider_validate_dest.py"
  "${ROOT}/services/api/app/services/provider_validate_net.py"
  "${ROOT}/services/auth/internal/grpc/provider_credentials.go"
  "${ROOT}/services/auth/internal/service/provider_credentials.go"
  "${ROOT}/services/proxy/internal/http/chat_provider.go"
  "${ROOT}/services/proxy/internal/credentials/resolver.go"
)
for f in "${log_targets[@]}"; do
  [[ -f "$f" ]] || continue
  if rg -n "${LOG_KEY_RE}" "$f" 2>/dev/null; then
    echo "forbidden secret log field key in ${f#"$ROOT"/}" >&2
    fail=1
  fi
done

# OpenAPI / schema export paths (when present).
shopt -s nullglob
openapi_paths=(
  "${ROOT}/services/api/openapi"*
  "${ROOT}/services/api/app/openapi"*
  "${ROOT}/docs/openapi"*
)
for p in "${openapi_paths[@]}"; do
  scan_sealed "openapi-export" "$p"
done
shopt -u nullglob

exit "${fail}"
