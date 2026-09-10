#!/usr/bin/env bash
# Fail if Management API provider schemas/OpenAPI leak sealed credential fields.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET="${ROOT}/services/api"

# Forbidden names in provider schemas / OpenAPI-facing modules.
PATTERNS=(
  'encrypted_api_key'
  'ciphertext'
  'wrapped_dek'
)

fail=0
for pat in "${PATTERNS[@]}"; do
  if rg -n --glob '*.py' --glob '!**/tests/**' "${pat}" \
    "${TARGET}/app/schemas/providers.py" \
    "${TARGET}/app/routers/providers.py" \
    "${TARGET}/app/services/providers.py" \
    2>/dev/null; then
    echo "provider credential leak pattern found: ${pat}" >&2
    fail=1
  fi
done

# Response models must not declare api_key (write request may).
if rg -n 'api_key' "${TARGET}/app/schemas/providers.py" | rg -v 'UpsertRequest|ApiKeyStr|api_key: ApiKeyStr'; then
  echo "unexpected api_key field outside upsert request schema" >&2
  fail=1
fi

exit "${fail}"
