#!/usr/bin/env bash
# Unit tests for coverage-responsepipeline-gate validation, filtering, and thresholds.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=coverage-responsepipeline-gate_lib.sh
source "$ROOT/infra/scripts/coverage-responsepipeline-gate_lib.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_eq() {
  local got="$1"
  local want="$2"
  local msg="$3"
  if [[ "$got" != "$want" ]]; then
    fail "$msg (got=$got want=$want)"
  fi
}

test_validate_min_coverage_rejects_non_integer() {
  if validate_min_coverage "abc" 2>/dev/null; then
    fail "expected non-integer MIN_COVERAGE to fail"
  fi
  if validate_min_coverage "95.5" 2>/dev/null; then
    fail "expected fractional MIN_COVERAGE to fail"
  fi
}

test_validate_min_coverage_accepts_integers() {
  validate_min_coverage "0"
  validate_min_coverage "95"
  validate_min_coverage "100"
}

test_filter_includes_fractional_line_ranges() {
  local input filtered
  input="$(mktemp)"
  filtered="$(mktemp)"

  cat >"$input" <<'EOF'
github.com/Rick1330/ibex-harness/services/proxy/internal/http/chat_provider.go:148.0,148.5 0 0
github.com/Rick1330/ibex-harness/services/proxy/internal/http/chat_provider.go:149.0,149.5 1 1
github.com/Rick1330/ibex-harness/services/proxy/internal/http/chat_provider.go:174.1,174.8 2 1
github.com/Rick1330/ibex-harness/services/proxy/internal/http/chat_provider.go:175.0,175.5 1 0
EOF

  grep 'chat_provider\.go' "$input" | filter_http_chat_provider_lines >"$filtered"
  local count
  count="$(wc -l <"$filtered" | tr -d ' ')"
  rm -f "$input" "$filtered"
  assert_eq "$count" "2" "fractional ranges 149 and 174 should be included"
}

test_filter_excludes_out_of_scope_lines() {
  local input filtered
  input="$(mktemp)"
  filtered="$(mktemp)"

  cat >"$input" <<'EOF'
github.com/Rick1330/ibex-harness/services/proxy/internal/http/chat_provider.go:120.0,120.5 1 1
github.com/Rick1330/ibex-harness/services/proxy/internal/http/chat_provider.go:200.0,200.5 1 1
EOF

  grep 'chat_provider\.go' "$input" | filter_http_chat_provider_lines >"$filtered"
  if [[ -s "$filtered" ]]; then
    rm -f "$input" "$filtered"
    fail "expected out-of-scope lines to be excluded"
  fi
  rm -f "$input" "$filtered"
}

test_merge_scoped_profiles_requires_selected_entries() {
  local tmp rp boot http filtered
  tmp="$(mktemp -d)"
  rp="$tmp/rp.out"
  boot="$tmp/boot.out"
  http="$tmp/http.out"
  filtered="$tmp/scoped.out"

  cat >"$rp" <<'EOF'
mode: set
github.com/Rick1330/ibex-harness/packages/responsepipeline/pipeline.go:10.0,20.0 5 4
EOF
  cat >"$boot" <<'EOF'
mode: set
github.com/Rick1330/ibex-harness/services/proxy/internal/bootstrap/wire.go:10.0,20.0 5 4
EOF
  cat >"$http" <<'EOF'
mode: set
github.com/Rick1330/ibex-harness/services/proxy/internal/http/router.go:10.0,20.0 5 4
EOF

  merge_scoped_profiles "$rp" "$boot" "$http" "$filtered"
  if grep -q 'wire.go' "$filtered"; then
    rm -rf "$tmp"
    fail "bootstrap profile should only include responsepipeline.go entries"
  fi
  if grep -q 'router.go' "$filtered"; then
    rm -rf "$tmp"
    fail "http profile should only include filtered chat_provider.go entries"
  fi
  if ! grep -q 'responsepipeline/pipeline.go' "$filtered"; then
    rm -rf "$tmp"
    fail "expected responsepipeline package entries in merged profile"
  fi
  rm -rf "$tmp"
}

test_threshold_pass_and_fail() {
  if ! check_coverage_threshold "95" "95"; then
    fail "95% should meet 95% threshold"
  fi
  if ! check_coverage_threshold "100" "95"; then
    fail "100% should meet 95% threshold"
  fi
  if check_coverage_threshold "0" "95"; then
    fail "0% should fail 95% threshold"
  fi
  if check_coverage_threshold "94.9" "95"; then
    fail "94.9% should fail 95% threshold"
  fi
  if ! check_coverage_threshold "0" "0"; then
    fail "0% should meet 0% threshold"
  fi
}

test_gate_entrypoint_rejects_invalid_min() {
  if MIN_COVERAGE=not-a-number bash "$ROOT/infra/scripts/coverage-responsepipeline-gate.sh" 2>/dev/null; then
    fail "gate entrypoint should reject invalid MIN_COVERAGE"
  fi
}

main() {
  test_validate_min_coverage_rejects_non_integer
  test_validate_min_coverage_accepts_integers
  test_filter_includes_fractional_line_ranges
  test_filter_excludes_out_of_scope_lines
  test_merge_scoped_profiles_requires_selected_entries
  test_threshold_pass_and_fail
  test_gate_entrypoint_rejects_invalid_min
  echo "coverage-responsepipeline-gate tests: ok"
}

main "$@"
