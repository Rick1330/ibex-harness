#!/usr/bin/env bash
# Run the documentation and site checks that match the current change set.
#
# Usage:
#   bash infra/scripts/agent-docs-check.sh [auto|fast|full|repo]
#
#   auto  (default) full site checks when site/ changed, otherwise fast checks
#                   when markdown or ledger files changed, otherwise nothing
#   fast            markdownlint on changed files + status-ledger claim check
#   full            site typecheck, lint, build, and check (claims/links/redirects)
#   repo            markdownlint across the whole repository + claim check
#
# Environment:
#   DOCS_BASE_REF   git ref to diff against (default: origin/main, then HEAD~1)
#
# Exit codes: 0 = all checks passed (or nothing to check), 1 = a check failed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

MODE="${1:-auto}"
BASE="${DOCS_BASE_REF:-}"

case "$MODE" in
  auto | fast | full | repo) ;;
  *)
    echo "usage: $0 [auto|fast|full|repo]" >&2
    exit 2
    ;;
esac

if [ -z "$BASE" ]; then
  if git rev-parse --verify -q origin/main >/dev/null 2>&1; then
    BASE="origin/main"
  elif git rev-parse --verify -q HEAD~1 >/dev/null 2>&1; then
    BASE="HEAD~1"
  fi
fi

if [ "$MODE" = "repo" ]; then
  echo "docs-check: mode=repo (whole repository)"
  FAILED=0
  echo "docs-check: markdownlint (repository)"
  if ! npx --yes markdownlint-cli2; then FAILED=1; fi
  echo "docs-check: status-ledger claim check"
  if ! pnpm --filter site check:claims; then FAILED=1; fi
  if [ "$FAILED" -ne 0 ]; then
    echo "docs-check: FAILED — fix the checks above." >&2
    exit 1
  fi
  echo "docs-check: OK"
  exit 0
fi

changed_files() {
  {
    if [ -n "$BASE" ]; then
      git diff --name-only "$BASE"...HEAD 2>/dev/null || true
    fi
    git diff --name-only 2>/dev/null || true
    git diff --cached --name-only 2>/dev/null || true
    git ls-files --others --exclude-standard 2>/dev/null || true
  } | sort -u
}

FILES="$(changed_files)"

if [ -z "$FILES" ]; then
  echo "docs-check: no changed files, nothing to do."
  exit 0
fi

MD_FILES="$(printf '%s\n' "$FILES" | grep -E '\.md$' || true)"
SITE_CHANGED="$(printf '%s\n' "$FILES" | grep -E '^site/' || true)"
LEDGER_CHANGED="$(printf '%s\n' "$FILES" | grep -E 'ledger\.ts|00-status-and-evidence\.md|05\.status-and-evidence\.md' || true)"

run_markdownlint() {
  if [ -z "$MD_FILES" ]; then
    return 0
  fi
  echo "docs-check: markdownlint ($(printf '%s\n' "$MD_FILES" | wc -l | tr -d ' ') changed file(s))"
  # --no-globs keeps this to the changed files instead of the repo-wide config globs.
  # shellcheck disable=SC2086
  if ! npx --yes markdownlint-cli2 --no-globs $MD_FILES; then
    FAILED=1
  fi
}

run_claims() {
  echo "docs-check: status-ledger claim check"
  if ! pnpm --filter site check:claims; then
    FAILED=1
  fi
}

run_site_full() {
  echo "docs-check: site typecheck"
  if ! pnpm site:typecheck; then FAILED=1; fi
  echo "docs-check: site lint"
  if ! pnpm site:lint; then FAILED=1; fi
  echo "docs-check: site build"
  if ! pnpm site:build; then FAILED=1; fi
  echo "docs-check: site claims, links, redirects"
  if ! pnpm site:check; then FAILED=1; fi
}

echo "docs-check: mode=$MODE base=${BASE:-none} changed=$(printf '%s\n' "$FILES" | wc -l | tr -d ' ')"

FAILED=0

case "$MODE" in
  fast)
    run_markdownlint
    if [ -n "$LEDGER_CHANGED" ]; then run_claims; fi
    ;;
  full)
    run_markdownlint
    run_site_full
    ;;
  auto)
    if [ -n "$SITE_CHANGED" ]; then
      run_markdownlint
      run_site_full
    elif [ -n "$MD_FILES" ] || [ -n "$LEDGER_CHANGED" ]; then
      run_markdownlint
      if [ -n "$LEDGER_CHANGED" ]; then run_claims; fi
    else
      echo "docs-check: no documentation-relevant changes."
    fi
    ;;
esac

if [ -n "$LEDGER_CHANGED" ]; then
  echo "docs-check: status ledger changed — confirm all three stay in sync:"
  echo "  engineering/architecture-v2/00-status-and-evidence.md"
  echo "  site/app/data/ledger.ts"
  echo "  site/content/docs/02.architecture/05.status-and-evidence.md"
fi

if [ "$FAILED" -ne 0 ]; then
  echo "docs-check: FAILED — fix the checks above before pushing." >&2
  exit 1
fi

echo "docs-check: OK"
