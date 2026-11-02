#!/usr/bin/env bash
# Regression tests for the tracked local-only file guard in check-repo-layout.sh.
# Each case builds a throwaway git index so the rejection branch is exercised
# without touching this checkout.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GUARD="$ROOT_DIR/.github/scripts/check-repo-layout.sh"
fail=0

# run_case <expected_exit> <expected_message|-> <label> <path>...
run_case() {
  local expected="$1" expected_message="$2" label="$3"
  shift 3
  local tmp log actual=0 output path
  tmp="$(mktemp -d)"
  # Keep the log outside the fixture repo: the guard rejects unexpected root files.
  log="$(mktemp)"

  (
    cd "$tmp"
    git init -q .
    mkdir -p .github/workflows engineering services/console
    printf '# Test\n' > README.md
    printf 'name: ci\n' > .github/workflows/ci.yml
    printf '# Notes\n' > engineering/notes.md
    for path in "$@"; do
      mkdir -p "$(dirname "$path")"
      printf '{}\n' > "$path"
    done
    git add -f -- README.md .github/workflows/ci.yml engineering/notes.md "$@"
    bash "$GUARD"
  ) >"$log" 2>&1 || actual=$?
  output="$(cat "$log")"
  rm -rf "$tmp" "$log"

  if [[ "$actual" -ne "$expected" ]]; then
    printf 'FAIL: %s: got exit %s, want %s\n%s\n' "$label" "$actual" "$expected" "$output" >&2
    fail=1
    return
  fi
  if [[ "$expected_message" != "-" ]] && ! grep -qF -- "$expected_message" <<<"$output"; then
    printf 'FAIL: %s: missing message %s\n%s\n' "$label" "$expected_message" "$output" >&2
    fail=1
    return
  fi
  printf 'PASS: %s\n' "$label"
}

run_case 0 - "clean tracked tree passes"
run_case 1 "Local-only file must not be tracked: opencode.json" \
  "root opencode.json is rejected" opencode.json
run_case 1 "Local-only file must not be tracked: services/console/opencode.json" \
  "nested opencode.json is rejected" services/console/opencode.json
run_case 1 "Local-only file must not be tracked: engineering/MODEL-POLICY.md" \
  "nested MODEL-POLICY.md is rejected" engineering/MODEL-POLICY.md
run_case 1 "Local-only file must not be tracked: services/console/LOOP.md" \
  "nested LOOP.md is rejected" services/console/LOOP.md
run_case 0 - "similarly named files are allowed" services/console/opencode.example.json

if ((fail != 0)); then
  echo "repo layout guard tests failed" >&2
  exit 1
fi

echo "repo layout guard tests passed"
