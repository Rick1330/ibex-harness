#!/usr/bin/env bash
# Shared helpers for coverage-responsepipeline-gate.sh (sourced, not executed).
# shellcheck disable=SC2034

validate_min_coverage() {
  local raw="${1:?usage: validate_min_coverage MIN_RAW}"
  if ! [[ "$raw" =~ ^[0-9]+$ ]]; then
    echo "MIN_COVERAGE must be an integer, got: $raw" >&2
    return 1
  fi
}

# Filter chat_provider.go profile lines to processResponseBody scope (lines 149–174).
filter_http_chat_provider_lines() {
  awk -F: '
    {
      split($2, range, ",")
      start = range[1]
      sub(/\..*$/, "", start)
      start += 0
      if (start >= 149 && start <= 174) print
    }
  '
}

merge_scoped_profiles() {
  local rp_profile="$1"
  local boot_profile="$2"
  local http_profile="$3"
  local filtered_out="$4"

  {
    grep -E '^mode:' "$rp_profile"
    grep -vE '^mode:' "$rp_profile" || true
    { grep -vE '^mode:' "$boot_profile" | grep 'responsepipeline\.go' || true; }
    { grep -vE '^mode:' "$http_profile" | grep 'chat_provider\.go' | filter_http_chat_provider_lines || true; }
  } >"$filtered_out"
}

coverage_pct_from_profile() {
  local profile="$1"
  go tool cover -func="$profile" | awk '/^total:/ { gsub(/%/,"",$3); print $3 }'
}

check_coverage_threshold() {
  local pct="$1"
  local min="$2"
  awk -v pct="$pct" -v min="$min" 'BEGIN { exit (pct + 0 >= min + 0) ? 0 : 1 }'
}
