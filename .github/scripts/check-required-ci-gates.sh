#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROTECTION="${ROOT}/.github/branch-protection-main.json"
CI_WORKFLOW="${ROOT}/.github/workflows/ci.yml"
SEMGREP_WORKFLOW="${ROOT}/.github/workflows/semgrep.yml"
SEMANTIC_WORKFLOW="${ROOT}/.github/workflows/semantic-pr.yml"

# Map each protected context to the workflow expected to emit it. The inventory
# drives iteration, so adding/removing a required context cannot silently escape
# this guard. Both the job id and effective displayed context name are checked.
	workflow_for_context() {
  case "$1" in
    ci-gate-repo|ci-gate-go|ci-gate-web|ci-gate-security|ci-gate-python|gitleaks) printf '%s\n' "$CI_WORKFLOW" ;;
    ci-gate-semgrep) printf '%s\n' "$SEMGREP_WORKFLOW" ;;
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

printf 'All %s protected contexts match exactly one workflow job name.\n' "${#contexts[@]}"
