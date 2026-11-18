#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROTECTION="${ROOT}/.github/branch-protection-main.json"
CI_WORKFLOW="${ROOT}/.github/workflows/ci.yml"
SEMGREP_WORKFLOW="${ROOT}/.github/workflows/semgrep.yml"
SEMANTIC_WORKFLOW="${ROOT}/.github/workflows/semantic-pr.yml"
MEMORY_BENCH_WORKFLOW="${ROOT}/.github/workflows/memory-benchmark.yml"

# Map each protected context to the workflow expected to emit it. The inventory
# drives iteration, so adding/removing a required context cannot silently escape
# this guard. Both the job id and effective displayed context name are checked.
	workflow_for_context() {
  case "$1" in
    ci-gate-repo|ci-gate-go|ci-gate-site|ci-gate-security|ci-gate-python|gitleaks) printf '%s\n' "$CI_WORKFLOW" ;;
    ci-gate-semgrep) printf '%s\n' "$SEMGREP_WORKFLOW" ;;
    ci-gate-memory-benchmark) printf '%s\n' "$MEMORY_BENCH_WORKFLOW" ;;
    semantic-pr-title) printf '%s\n' "$SEMANTIC_WORKFLOW" ;;
    *) return 1 ;;
  esac
	}

contexts_output="$(jq -er '.required_status_checks.checks | map(.context) | .[]' "$PROTECTION")"
mapfile -t contexts <<< "$contexts_output"
if (( ${#contexts[@]} == 0 )); then
  echo 'Required-check inventory is empty' >&2
  exit 1
fi

seen=' '
for context in "${contexts[@]}"; do
  [[ -n "$context" ]] || { echo 'Required-check inventory contains an empty context' >&2; exit 1; }
  if [[ "$seen" == *" $context "* ]]; then
    printf 'Required-check inventory contains duplicate context %s\n' "$context" >&2
    exit 1
  fi
  seen+="$context "

  workflow="$(workflow_for_context "$context")" || {
    printf 'No workflow mapping exists for protected context %s\n' "$context" >&2
    exit 1
  }
  count="$(grep -Ec "^    name: ${context//./\\.}$" "$workflow" || true)"
  if [[ "$count" != 1 ]]; then
    printf 'Protected context %s must appear exactly once as a workflow job name in %s (found %s)\n' \
      "$context" "${workflow#"$ROOT"/}" "$count" >&2
    exit 1
  fi
  printf '%s: %s\n' "$context" "${workflow#"$ROOT"/}"
done

# The two newly added aggregate gates additionally have change-detection
# semantics that cannot be inferred from their display name alone.
grep -Fq 'CHANGES_RESULT: ${{ needs.changes.result }}' "$SEMGREP_WORKFLOW" || {
  echo 'ci-gate-semgrep must pass the path-change detector result' >&2; exit 1;
}
grep -Fq 'changes_result="${2:?changes_result required (must be success)}"' "${ROOT}/.github/scripts/evaluate-ci-gate.sh" || {
  echo 'shared aggregate gate must require the detector result' >&2; exit 1;
}
grep -Fq 'evaluate-ci-gate.sh "$AREA_ACTIVE" "$CHANGES_RESULT" "$SEMGREP_RESULT"' "$SEMGREP_WORKFLOW" || {
  echo 'ci-gate-semgrep must pass the detector result to the shared gate' >&2; exit 1;
}
grep -Fq 'evaluate-ci-gate.sh "${{ needs.changes.outputs.run_python }}" "${{ needs.changes.result }}"' "$CI_WORKFLOW" || {
  echo 'ci-gate-python must pass the detector result to the shared gate' >&2; exit 1;
}

# ci-gate-memory-benchmark is published by an always-run aggregate in a separate workflow.
# It must take the detector's verdict and the active flag, or a path-filtered skip would be
# indistinguishable from "not due".
grep -Fq 'evaluate-memory-benchmark-gate.sh' "$MEMORY_BENCH_WORKFLOW" || {
  echo 'ci-gate-memory-benchmark must evaluate through evaluate-memory-benchmark-gate.sh' >&2; exit 1;
}
grep -Fq 'BENCH_ACTIVE: ${{ needs.detect-memory-bench-changes.outputs.bench_active }}' "$MEMORY_BENCH_WORKFLOW" || {
  echo 'ci-gate-memory-benchmark must pass the detector active flag' >&2; exit 1;
}
grep -Fq 'DETECTOR_RESULT: ${{ needs.detect-memory-bench-changes.result }}' "$MEMORY_BENCH_WORKFLOW" || {
  echo 'ci-gate-memory-benchmark must pass the detector result' >&2; exit 1;
}

printf 'All %s protected contexts match exactly one workflow job name.\n' "${#contexts[@]}"

# --- declared vs live required contexts ------------------------------------
# Everything above proves the record and the guard agree with each other. The live
# rule is a separate object that no commit can change: a context declared here but
# absent there is a gate that cannot block a merge, which is how this repository
# carried nine declared and five enforced contexts without anyone noticing. Compare
# them when the credential can read the rule, and say so when it cannot.
#
# Reading branch protection requires repository administration. GITHUB_TOKEN does not
# have it, so the unreadable case is a printed SKIP, not a failure — otherwise this
# job could never pass. The comparison itself is exercised by
# infra/scripts/test-ci-tiering.sh through IBEX_LIVE_REQUIRED_CONTEXTS, so it is known
# to bite rather than assumed to.
repository_slug() {
  if [[ -n "${GITHUB_REPOSITORY:-}" ]]; then
    printf '%s\n' "$GITHUB_REPOSITORY"
    return 0
  fi
  command -v gh >/dev/null 2>&1 || return 1
  gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null
}

live_required_contexts() {
  if [[ -n "${IBEX_LIVE_REQUIRED_CONTEXTS:-}" ]]; then
    tr ',' '\n' <<<"$IBEX_LIVE_REQUIRED_CONTEXTS" |
      sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' |
      sed '/^$/d'
    return 0
  fi
  command -v gh >/dev/null 2>&1 || return 1
  local repo
  repo="$(repository_slug)" || return 1
  [[ -n "$repo" ]] || return 1
  # A missing or null value is a readable rule with nothing enforced, not a failed
  # read. `.required_status_checks.contexts[]` errors on both (jq exits non-zero,
  # gh returns non-zero, the caller's `if` takes the warning branch and exits 0), so
  # a rule that enforces no context at all reported success while every declared
  # context stayed unenforced. `// []` makes that a successful read of zero checks,
  # which the empty-list branch below reports. A genuine failure (no gh, no auth,
  # non-200) still exits non-zero here and still takes the warning branch.
  gh api "repos/${repo}/branches/main/protection" \
    --jq '(.required_status_checks.contexts // [])[]' 2>/dev/null
}

# Retrieval failure and a successfully-read-but-empty rule are different facts, and the
# old `&& [[ -n "$live" ]]` collapsed them: an empty list normalised to nothing, skipped
# the comparison, printed the "could not read" warning and exited 0 — while every
# declared context was unenforced. A read that succeeds always compares.
if live="$(live_required_contexts)"; then
  mapfile -t enforced_contexts < <(sed '/^$/d' <<<"$live")
  unenforced=()
  for context in "${contexts[@]}"; do
    enforced=0
    for candidate in "${enforced_contexts[@]}"; do
      # Exact equality, one array element at a time. The old test asked whether the
      # joined list contained " $context ", so a *different* context that embeds a
      # declared name ("legacy ci-gate-site") counted as enforcing "ci-gate-site" —
      # the same defect as a skipped comparison, in the forgiving direction.
      if [[ "$candidate" == "$context" ]]; then
        enforced=1
        break
      fi
    done
    (( enforced )) || unenforced+=("$context")
  done
  if (( ${#unenforced[@]} > 0 )); then
    if (( ${#enforced_contexts[@]} == 0 )); then
      printf 'The live main branch rule reports zero required status checks.\n' >&2
    fi
    printf 'Declared but NOT enforced by the live main branch rule: %s\n' "${unenforced[*]}" >&2
    printf 'Each of those cannot block a merge. Adding them is an owner action; this script must not take it:\n' >&2
    printf '  gh api --method PUT repos/%s/branches/main/protection --input .github/branch-protection-main.json\n' \
      "$(repository_slug 2>/dev/null || printf '<owner>/<repo>')" >&2
    if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
      printf '### Required checks: %s declared, %s enforced\n\nNot enforced: %s\n' \
        "${#contexts[@]}" "${#enforced_contexts[@]}" "${unenforced[*]}" >>"$GITHUB_STEP_SUMMARY"
    fi
    exit 1
  fi
  printf 'All %s declared contexts are enforced by the live main rule.\n' "${#contexts[@]}"
else
  printf 'WARNING: the live main branch protection is not readable with this credential, so declared-but-unenforced contexts were NOT compared.\n' >&2
  printf '         Branch protection needs repository admin. Run this script with an admin token, or set IBEX_LIVE_REQUIRED_CONTEXTS to the enforced list, to check it.\n' >&2
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    printf '### Required checks: live rule not readable\n\nDeclared-but-unenforced contexts were not compared (needs an admin token).\n' >>"$GITHUB_STEP_SUMMARY"
  fi
fi
