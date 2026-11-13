#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE="${ROOT}/.github/scripts/evaluate-memory-benchmark-gate.sh"

expect_status() {
  local expected="$1" label="$2"
  shift 2
  local actual=0
  bash "$GATE" "$@" >/dev/null 2>&1 || actual=$?
  if [[ "$actual" -ne "$expected" ]]; then
    printf 'FAIL: %s: got exit %s, want %s\n' "$label" "$actual" "$expected" >&2
    exit 1
  fi
  printf 'PASS: %s\n' "$label"
}

# Not due: the collectors are skipped by design, so their results are ignored.
expect_status 0 "inactive paths pass with skipped collectors" false success skipped skipped skipped
expect_status 0 "inactive paths pass with no collector results" false success
# A failed or missing detector must never be read as "not due".
expect_status 1 "failed detector blocks the gate" false failure
expect_status 1 "missing detector result blocks the gate" false "" success
expect_status 2 "invalid bench_active is a usage error" maybe success success
# Due: every collector must have run and passed. Unlike the general CI gate, `skipped`
# is not acceptable -- it means a due collector did not run.
expect_status 0 "all collectors successful" true success success success success
expect_status 1 "skipped collector blocks when due" true success success skipped success
expect_status 1 "failed collector blocks when due" true success success failure success
expect_status 1 "cancelled collector blocks when due" true success cancelled success success
expect_status 1 "unknown collector state blocks when due" true success success pending success
expect_status 1 "no collector results blocks when due" true success

# --- detector filter coverage ---------------------------------------------
# ci-gate-memory-benchmark is only meaningful if the detector activates on every input
# the collectors consume. A collector that loads an unmodified script, schema, or
# lockfile measures a tree the PR did not change, so a regression in that file passes
# the gate it should have failed. The patterns are read from the workflow rather than
# restated here, so dropping one, or reformatting the filter block out of reach, fails.
WORKFLOW="${ROOT}/.github/workflows/memory-benchmark.yml"

filter_patterns="$(
  awk '
    /^            memory_bench:$/ { inside = 1; next }
    !inside { next }
    /^[[:space:]]*$/ { next }
    /^              #/ { next }
    /^              - / {
      line = $0
      sub(/^              - /, "", line)
      gsub(/^'"'"'/, "", line)
      gsub(/'"'"'$/, "", line)
      print line
      next
    }
    { exit }
  ' "$WORKFLOW"
)"

if [[ -z "$filter_patterns" ]]; then
  printf 'FAIL: no memory_bench filter patterns parsed from %s\n' "$WORKFLOW" >&2
  exit 1
fi
printf 'PASS: parsed %s memory_bench filter pattern(s)\n' "$(wc -l <<<"$filter_patterns" | tr -d ' ')"

# picomatch subset used by the filter: `**` spans separators, `*` does not, `?` is one
# non-separator character. Anything else is matched literally.
glob_to_ere() {
  local glob="$1" out="" i=0 c len="${#1}"
  while ((i < len)); do
    c="${glob:i:1}"
    if [[ "$c" == '*' ]]; then
      if ((i + 1 < len)) && [[ "${glob:i+1:1}" == '*' ]]; then
        out+='.*'
        i=$((i + 2))
      else
        out+='[^/]*'
        i=$((i + 1))
      fi
      continue
    fi
    case "$c" in
      '?') out+='[^/]' ;;
      '.') out+='\.' ;;
      '+' | '(' | ')' | '[' | ']' | '{' | '}' | '^' | '$' | '|' | "\\") out+="\\$c" ;;
      *) out+="$c" ;;
    esac
    i=$((i + 1))
  done
  printf '%s' "$out"
}

matches_any_pattern() {
  local path="$1" pattern re
  while IFS= read -r pattern; do
    [[ -n "$pattern" ]] || continue
    re="^$(glob_to_ere "$pattern")$"
    if [[ "$path" =~ $re ]]; then
      return 0
    fi
  done <<<"$filter_patterns"
  return 1
}

# Every input a collector reads: benched code, benches, schemas, validators, the scripts
# the collector steps call, the migrations those scripts apply, and the dependency files
# they install from.
required_inputs=(
  services/memory/uv.lock
  benchmarks/memory/ranking_quality/regression_gate.py
  benchmarks/memory/write_pipeline/bench_write_pipeline.py
  benchmarks/data-schema/hnsw-benchmark-data.schema.json
  benchmarks/data-schema/ranking-quality-benchmark-data.schema.json
  benchmarks/data-schema/write-pipeline-benchmark-data.schema.json
  benchmarks/scripts/check_hnsw_gate_status.py
  benchmarks/scripts/validate_published_hnsw.py
  benchmarks/scripts/validate_published_memory_suite.py
  infra/scripts/memory-bench.sh
  infra/scripts/db-migrate.sh
  infra/scripts/memory-uv-sync.sh
  infra/scripts/build-authclient-wheel.sh
  infra/scripts/build-ibex-async-db-wheel.sh
  infra/scripts/build-ibex-idempotency-wheel.sh
  infra/migrations/postgres/000001_init_schemas.up.sql
  infra/migrations/postgres/cmd/migrate/main.go
  go.mod
  go.sum
  packages/authclient/pyproject.toml
  packages/ibex_async_db/uv.lock
  packages/ibex_idempotency/pyproject.toml
  .github/requirements/jsonschema.in
  .github/requirements/jsonschema.txt
  .github/workflows/memory-benchmark.yml
)

for path in "${required_inputs[@]}"; do
  if [[ ! -e "$ROOT/$path" ]]; then
    printf 'FAIL: filter coverage test names %s, which does not exist\n' "$path" >&2
    exit 1
  fi
  if ! matches_any_pattern "$path"; then
    printf 'FAIL: memory_bench filter does not activate on %s\n' "$path" >&2
    exit 1
  fi
  printf 'PASS: filter activates on %s\n' "$path"
done

# Negative control: the matcher must stay narrow. If it matched everything the coverage
# cases above would prove nothing.
for path in services/proxy/cmd/proxy/main.go README.md; do
  if matches_any_pattern "$path"; then
    printf 'FAIL: filter matcher is over-broad; %s must not activate the gate\n' "$path" >&2
    exit 1
  fi
  printf 'PASS: filter stays inactive on %s\n' "$path"
done

printf 'All memory benchmark gate regression cases passed.\n'
