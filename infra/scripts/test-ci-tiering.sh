#!/usr/bin/env bash
# Regression tests for the PR vs main/nightly CI tiering policy.
#
# The workflow YAML is the source of truth; these assertions catch an accidental
# change to an event condition, a missing nightly prerequisite, or a Docker
# Publish path that stops validating files copied into an image.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CI="$ROOT/.github/workflows/ci.yml"
DOCKER="$ROOT/.github/workflows/docker-publish.yml"
fail=0

pass() { printf 'PASS: %s\n' "$1"; }
bad() {
  printf 'FAIL: %s\n' "$1" >&2
  fail=1
}

job_if() {
  local job="$1"
  awk -v key="  ${job}:" '
    $0 == key { found = 1 }
    found && /^    if:/ { print; exit }
    found && /^  [a-z0-9_-]+:$/ && $0 != key { exit }
  ' "$CI"
}

job_block() {
  local job="$1"
  awk -v key="  ${job}:" '
    $0 == key { found = 1 }
    found && /^  [a-z0-9_-]+:$/ && $0 != key { exit }
    found { print }
  ' "$CI"
}

file_block() {
  local file="$1" job="$2"
  awk -v key="  ${job}:" '
    $0 == key { found = 1 }
    found && /^  [a-z0-9_-]+:$/ && $0 != key { exit }
    found { print }
  ' "$file"
}

# --- schedule ownership ----------------------------------------------------
if grep -Fq 'cron: "0 3 * * *"' "$CI"; then
  pass "ci.yml owns the daily 03:00 UTC schedule"
else
  bad "ci.yml is missing the daily 03:00 UTC schedule"
fi

if [[ -f "$ROOT/.github/workflows/nightly.yml" ]]; then
  bad "nightly.yml must not duplicate the ci.yml schedule"
else
  pass "nightly.yml is removed"
fi

force_full="$(grep -m1 'force-full:' "$CI")"
for token in "github.event_name == 'schedule'" "github.event_name == 'push'" "inputs.force_full == true"; do
  if grep -Fq "$token" <<<"$force_full"; then
    pass "detector force-full includes $token"
  else
    bad "detector force-full is missing $token"
  fi
done

# --- full-matrix jobs ------------------------------------------------------
full_jobs=(
  go-fuzz
  e2e-smoke-p3-memory
  e2e-smoke-p35
  verify-phase25
  memory-security-integration
  security-integration-p35
  worker-integration
  relay-integration
  mcp-operator-integration
  idempotency-conformance
)

for job in "${full_jobs[@]}"; do
  cond="$(job_if "$job")"
  if [[ -z "$cond" ]]; then
    bad "$job has no job-level if condition"
    continue
  fi
  for token in "github.event_name == 'push'" "github.event_name == 'schedule'" "inputs.force_full == true"; do
    if ! grep -Fq "$token" <<<"$cond"; then
      bad "$job does not run on $token"
    fi
  done
  if ! grep -Fq "run_go" <<<"$cond" && ! grep -Fq "run_python" <<<"$cond"; then
    bad "$job has no path-filter fallback for ordinary manual runs"
  fi
done
pass "$((${#full_jobs[@]})) full-matrix jobs keep push/schedule/manual-full conditions"

# --- scheduled OSV ---------------------------------------------------------
osv_cond="$(job_if osv-scan)"
if grep -Fq "github.event_name != 'schedule'" <<<"$osv_cond"; then
  bad "osv-scan still excludes schedule"
else
  pass "osv-scan runs on the scheduled full matrix"
fi
if ! grep -Fq "run_security" <<<"$osv_cond"; then
  bad "osv-scan is not tied to the security area"
fi

# --- nightly gate prerequisites -------------------------------------------
nightly="$(job_block ci-gate-nightly)"
for prerequisite in proto-contract db-migrate-smoke; do
  if grep -Fq -- "- $prerequisite" <<<"$nightly"; then
    pass "ci-gate-nightly includes $prerequisite"
  else
    bad "ci-gate-nightly is missing $prerequisite"
  fi
done

# --- Docker Publish validates copied image inputs -------------------------
for path in \
  "services/**/Dockerfile" \
  "services/**/app/**" \
  "services/**/scripts/**" \
  "services/auth/**" \
  "services/proxy/**" \
  "services/context/**" \
  "services/console/**" \
  "services/relay/**" \
  "infra/provider-capabilities/**" \
  "services/**/pyproject.toml" \
  "services/**/uv.lock" \
  "packages/**"; do
  if grep -Fq -- "'$path'" "$DOCKER"; then
    pass "Docker Publish PR filter includes $path"
  else
    bad "Docker Publish PR filter is missing $path"
  fi
done

if (( fail != 0 )); then
  echo "CI tiering policy tests failed" >&2
  exit 1
fi

# --- tag release path ------------------------------------------------------
# release-docker.yml calls docker-publish.yml on a tag push. A reusable
# workflow inherits the caller's event, so resolve-tag must accept `push`;
# otherwise every publish job is skipped and the manifest has no digests.
resolve_if="$(file_block "$DOCKER" resolve-tag)"
if grep -Fq "github.event_name == 'push' && github.ref_type == 'tag'" <<<"$resolve_if"; then
  pass "docker-publish resolve-tag accepts a tag push"
else
  bad "docker-publish resolve-tag does not accept a tag push"
fi
if grep -Fq 'push)' <<<"$resolve_if" && grep -Fq 'GITHUB_REF_NAME' <<<"$resolve_if"; then
  pass "docker-publish resolves the tag for push events"
else
  bad "docker-publish has no push branch in the tag resolver"
fi

release_docker="$ROOT/.github/workflows/release-docker.yml"
manifest_block="$(file_block "$release_docker" release-manifest)"
if grep -Eq '^    needs: .*tagged-docker-publish' <<<"$manifest_block"; then
  pass "release-manifest runs after tagged-docker-publish"
else
  bad "release-manifest does not depend on tagged-docker-publish"
fi
if grep -Eq '^    needs: .*verify-published-images' <<<"$manifest_block"; then
  pass "release-manifest runs after the published images are verified"
else
  bad "release-manifest does not depend on verify-published-images"
fi
if grep -Fq 'gh release upload "$TAG" release-manifest.json' <<<"$manifest_block"; then
  pass "tagged release uploads the manifest"
else
  bad "tagged release does not upload the manifest"
fi
if grep -Fq 'needs: validate-tag' "$release_docker"; then
  pass "image publication waits for tag validation"
else
  bad "image publication does not wait for tag validation"
fi

# A tag push must not report success when every publish job was skipped: the
# called workflow's status is not evidence, so release-docker.yml asserts the
# images, and docker-publish has a terminal gate for the same condition.
verify_block="$(file_block "$release_docker" verify-published-images)"
if grep -Fq 'verify-release-images.sh' <<<"$verify_block" &&
  grep -Fq 'always()' <<<"$verify_block"; then
  pass "tagged release asserts the published images even when publishing was skipped"
else
  bad "tagged release does not assert the published images"
fi
gate_block="$(file_block "$DOCKER" publish-gate)"
if grep -Fq 'always()' <<<"$gate_block" &&
  grep -Fq "github.event_name != 'pull_request'" <<<"$gate_block" &&
  grep -Fq 'exit 1' <<<"$gate_block"; then
  pass "docker-publish gate fails when a publish job did not succeed"
else
  bad "docker-publish has no terminal gate for skipped publish jobs"
fi

publish_services="$(grep -E '^  push-[a-z0-9-]+:$' "$DOCKER" | sed -E 's/^  push-(.+):$/\1/' | sort)"
mapfile -t services_lists < <(
  grep -oE -- '--services [a-z0-9,-]+' "$release_docker" | awk '{print $2}'
)
if (( ${#services_lists[@]} == 0 )); then
  bad "release-docker.yml names no services"
fi
# Every call site must list exactly the published services; the verification and
# the manifest are generated from the same set, so they cannot drift apart.
for services_list in "${services_lists[@]}"; do
  if [[ "$(tr ',' '\n' <<<"$services_list" | sort)" == "$publish_services" ]]; then
    pass "services match the docker-publish push jobs ($services_list)"
  else
    bad "services do not match the docker-publish push jobs ($services_list)"
  fi
done

# --- published images are gated and evidenced ------------------------------
# P1-50: a push-* job is the only way an image reaches the registry, so every
# push job needs the amd64 build whose tar the scan gate reads, and the scan
# job itself. A publish job without one of them ships an unscanned image.
missing_gates=()
for service in $publish_services; do
  for prefix in build scan-image; do
    grep -Fxq "  ${prefix}-${service}:" "$DOCKER" || missing_gates+=("${prefix}-${service}")
  done
done
if (( ${#missing_gates[@]} == 0 )); then
  pass "every push-* job has a build and a scan gate ($(wc -w <<<"$publish_services") images)"
else
  bad "published images without a build or scan gate: ${missing_gates[*]}"
fi

# P1-09: one SPDX SBOM per published image, generated from the digest the push
# job published, and attached to the tagged release. An SBOM for an image that
# is not fed into the generator is an image with no evidence asset.
sbom_block="$(file_block "$DOCKER" sbom-images)"
if grep -Fq -- '--output spdx-json' <<<"$sbom_block" &&
  grep -Fq '.sbom.spdx.json' <<<"$sbom_block"; then
  pass "docker-publish generates one SPDX SBOM per published image"
else
  bad "docker-publish has no per-image SPDX SBOM step"
fi
missing_sbom=()
for service in $publish_services; do
  grep -Fq -- "- push-${service}" <<<"$sbom_block" || missing_sbom+=("$service")
done
if (( ${#missing_sbom[@]} == 0 )); then
  pass "the SBOM job consumes every push job digest"
else
  bad "the SBOM job ignores published images: ${missing_sbom[*]}"
fi
if grep -Fq 'SPDXRef-DocumentRoot' <<<"$sbom_block"; then
  pass "each SBOM is asserted to name the digest it describes"
else
  bad "the SBOM job does not bind a document to its image digest"
fi
if grep -Fq 'sboms/*.sbom.spdx.json' <<<"$manifest_block"; then
  pass "tagged release uploads the per-image SBOMs"
else
  bad "tagged release does not upload the per-image SBOMs"
fi

if (( fail != 0 )); then
  echo "CI tiering policy tests failed" >&2
  exit 1
fi

echo "CI tiering policy tests passed"
