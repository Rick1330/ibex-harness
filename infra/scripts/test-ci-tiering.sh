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

# --- helpers for edge assertions -------------------------------------------
# `needs:` is inline (`needs: [a, b]`) in most jobs and a list in the aggregates.
# Both spellings are normalised to one job name per line, so an assertion reads
# the edge and not the fact that a name appears somewhere in the block.
needs_tokens() {
  local file="$1" job="$2"
  file_block "$file" "$job" |
    awk '
      /^    needs:/ { pull = 1; sub(/^    needs:[[:space:]]*/, ""); print; next }
      pull && /^      - / { sub(/^      -[[:space:]]*/, ""); print; next }
      pull { exit }
    ' |
    tr -d '[]' | tr ',' '\n' | tr -d ' \r' | sed '/^$/d'
}

# The push job's published digest must come from a step that exists in it,
# otherwise `outputs.digest` resolves to the empty string and every consumer
# (SBOM, attestation, cosign, manifest) silently binds to nothing.
digest_step_id() {
  grep -oE 'digest: *\$\{\{ *steps\.[A-Za-z0-9_-]+\.outputs\.digest *\}\}' <<<"$1" |
    sed -E 's/.*steps\.([A-Za-z0-9_-]+)\.outputs.*/\1/' | head -1
}

# Root-level files copied into an image (go.mod, .npmrc, …). The token must be a
# regular file at the repository root: `COPY packages ./packages` and a trailing
# backslash name directories, which the directory globs already cover, while
# `COPY package.json …` names one file that a filter list can forget.
#
# Three parsing hazards, all handled here rather than by the caller:
#   * A COPY continued with a trailing backslash is one instruction. Reading only
#     the first line (`COPY package.json \`) missed the second line of sources,
#     so a file copied next to it — the real .npmrc case — could lose its trigger
#     without this test noticing. Continuations are joined before extraction, the
#     way the Dockerfile parser does it.
#   * `COPY --from=<stage>` reads from an earlier stage (or another image), not
#     from the repository, so its sources are not build inputs here. `--chown=`
#     and `--chmod=` are flag tokens, skipped by the same `--` rule without
#     hiding the sources that follow them.
#   * `COPY ["package.json", "./"]` is the JSON form of the same instruction. Its
#     tokens carry brackets, quotes and commas, so no token ever matched a
#     repository file and the whole instruction was skipped.
root_copy_sources() {
  awk '
    { if (pending != "") { $0 = pending " " $0; pending = "" } }
    /\\[[:space:]]*$/ { sub(/\\[[:space:]]*$/, ""); pending = $0; next }
    { print }
    END { if (pending != "") print pending }
  ' "$1" | awk '
    /^COPY / {
      gsub(/[][",]/, " ")
      for (i = 2; i <= NF; i++) if ($i ~ /^--from=/) next
      for (i = 2; i <= NF; i++) {
        if ($i ~ /^--/) continue
        if ($i ~ /\//) continue
        print $i
      }
    }
  ' | while read -r candidate; do
    [[ -f "$ROOT/${candidate}" ]] && printf '%s\n' "$candidate"
  done
}

# --- published images are gated and evidenced ------------------------------
# P1-50: a push-* job is the only way an image reaches the registry, so every
# push job needs the amd64 build whose tar the scan gate reads and the scan job
# itself. Existence of the two jobs is not the gate; the ordering edge is. A push
# job that does not `needs` its scan job still publishes — removing one name from
# one `needs:` list used to pass this test — so the assertions read the edges.
broken_edges=()
for service in $publish_services; do
  tokens="$(needs_tokens "$DOCKER" "push-${service}")"
  grep -Fxq "scan-image-${service}" <<<"$tokens" ||
    broken_edges+=("push-${service} does not need scan-image-${service}")
  grep -Fxq "resolve-tag" <<<"$tokens" ||
    broken_edges+=("push-${service} does not need resolve-tag")
  for prefix in build scan-image; do
    grep -Fxq "  ${prefix}-${service}:" "$DOCKER" ||
      broken_edges+=("push-${service} has no ${prefix}-${service} job")
  done
done
if (( ${#broken_edges[@]} == 0 )); then
  pass "every push-* job needs its own scan gate and has a build gate ($(wc -w <<<"$publish_services") images)"
else
  bad "publish ordering is broken: ${broken_edges[*]}"
fi

missing_digest=()
unproduced_digest=()
for service in $publish_services; do
  push_block="$(file_block "$DOCKER" "push-${service}")"
  step_id="$(digest_step_id "$push_block" || true)"
  if [[ -z "$step_id" ]]; then
    missing_digest+=("push-${service}")
  elif ! grep -Eq "^[[:space:]]+id: ${step_id}$" <<<"$push_block"; then
    unproduced_digest+=("push-${service} (no step id ${step_id})")
  fi
done
if (( ${#missing_digest[@]} == 0 )); then
  pass "every push-* job exposes a digest output"
else
  bad "push jobs with no digest output: ${missing_digest[*]}"
fi
if (( ${#unproduced_digest[@]} == 0 )); then
  pass "every push-* digest output names a step that exists in that job"
else
  bad "digest outputs naming a step the job does not have: ${unproduced_digest[*]}"
fi

# P1-09: one SPDX SBOM per published image, generated from the digest the push
# job published, and attached to the tagged release. An SBOM for an image that
# is not fed into the generator is an image with no evidence asset, and a loop
# entry that names the wrong job's digest binds the document to the wrong image,
# so the loop is compared against the push jobs in both directions.
sbom_block="$(file_block "$DOCKER" sbom-images)"
if grep -Fq -- '--output spdx-json' <<<"$sbom_block" &&
  grep -Fq '.sbom.spdx.json' <<<"$sbom_block"; then
  pass "docker-publish generates one SPDX SBOM per published image"
else
  bad "docker-publish has no per-image SPDX SBOM step"
fi

sbom_loop="$(awk '
  /<<EOF/ { inloop = 1; next }
  inloop && /^[[:space:]]*EOF$/ { exit }
  inloop { sub(/^[[:space:]]+/, ""); if ($0 != "") print }
' <<<"$sbom_block")"
if [[ -z "$sbom_loop" ]]; then
  bad "docker-publish has no SBOM digest loop"
fi
loop_services="$(awk '{print $1}' <<<"$sbom_loop" | sed '/^$/d' | sort)"

missing_sbom=()
for service in $publish_services; do
  grep -Fxq "$service" <<<"$loop_services" ||
    missing_sbom+=("${service} is missing from the SBOM loop")
done
if (( ${#missing_sbom[@]} == 0 )); then
  pass "the SBOM loop contains every push job"
else
  bad "the SBOM loop is incomplete: ${missing_sbom[*]}"
fi

# Every loop entry must be a published image: a service in the loop with no
# push-* job asks for a digest nothing produces, which is the same defect from
# the other side.
sbom_needs="$(needs_tokens "$DOCKER" sbom-images | sort)"
orphan_sbom=()
extra_sbom=()
while read -r service; do
  [[ -n "$service" ]] || continue
  grep -Fxq "push-${service}" <<<"$sbom_needs" ||
    orphan_sbom+=("the SBOM loop generates ${service} but no push-${service} job produces it")
done <<<"$loop_services"
for service in $publish_services; do
  grep -Fxq "push-${service}" <<<"$sbom_needs" ||
    extra_sbom+=("push-${service}")
done
if (( ${#orphan_sbom[@]} == 0 && ${#extra_sbom[@]} == 0 )); then
  pass "the SBOM job depends on exactly the push jobs its loop generates for"
else
  bad "SBOM job/push-job mismatch: ${orphan_sbom[*]} ${extra_sbom[*]}"
fi

# The loop line, the env var it reads, and the output it binds must name the same
# service. Names alone are not enough: `console ${CONSOLE_DIGEST}` passing while
# CONSOLE_DIGEST reads needs.push-relay.outputs.digest binds the wrong document.
unbound_digest=()
while read -r line; do
  [[ -n "$line" ]] || continue
  service="${line%% *}"
  var="${line##* }"
  var="${var#\$\{}"
  var="${var%\}}"
  grep -Fq -- "${var}: \${{ needs.push-${service}.outputs.digest }}" <<<"$sbom_block" ||
    unbound_digest+=("${service}: ${var} is not needs.push-${service}.outputs.digest")
done <<<"$sbom_loop"
if (( ${#unbound_digest[@]} == 0 )); then
  pass "each SBOM loop entry binds its own push job's digest"
else
  bad "the SBOM job binds the wrong digest: ${unbound_digest[*]}"
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

# --- copied image inputs are triggers --------------------------------------
# A file copied into an image build must trigger that build. Devin's finding: the
# console Dockerfile copies the root workspace config, but an .npmrc-only change
# matched no docker-publish path entry, and after merge the detector left
# run_docker false, so the publish skipped and :latest kept the previous install
# layout while the merged source used the new one. The lists below are derived
# from the Dockerfiles so a COPY line that grows a file fails here instead of
# being found after a release.
filter_block() {
  local file="$1" key="$2"
  awk -v k="${key}:" '$0 == k { f = 1 } f && /^[a-z]+:$/ && $0 != k { exit } f { print }' "$file"
}
FILTERS="$ROOT/.github/path-filters.yml"
# One line per input the console build copies but no trigger names, across the
# three lists a copied file has to appear in. Split out of the caller so the
# fixture below can be run against filters that are missing a name on purpose:
# an assertion nobody has seen fail is not known to work.
console_trigger_gaps() {
  local dockerfile="$1" workflow="$2" filters="$3" input
  while read -r input; do
    [[ -n "$input" ]] || continue
    grep -Fq -- "'${input}'" "$workflow" ||
      printf '%s is not in the Docker Publish PR filter\n' "$input"
    grep -Fq -- "- '${input}'" <<<"$(filter_block "$filters" docker)" ||
      printf '%s does not set run_docker\n' "$input"
    grep -Fq -- "- '${input}'" <<<"$(filter_block "$filters" console)" ||
      printf '%s does not run the console-quality gate\n' "$input"
  done <<<"$(root_copy_sources "$dockerfile")"
}

mapfile -t missing_console_inputs < <(
  console_trigger_gaps "$ROOT/services/console/Dockerfile" "$DOCKER" "$FILTERS"
)
if (( ${#missing_console_inputs[@]} == 0 )); then
  pass "every root file the console Dockerfile copies is a trigger for its build"
else
  bad "console image inputs with no trigger: ${missing_console_inputs[*]}"
fi

# Fixture: one COPY continued onto a second line, one stage-sourced COPY, one COPY
# behind a --chown/--chmod prefix, and one JSON-form COPY. The expected set is
# asserted exactly, so a matcher that reads only the first line, treats a stage
# source as a repository input, or skips the JSON form fails here.
fixture_dir="$(mktemp -d)"
trap 'rm -rf "$fixture_dir"' EXIT
fixture_dockerfile="$fixture_dir/Dockerfile"
cat >"$fixture_dockerfile" <<'EOF'
FROM node AS build
COPY package.json \
     .npmrc ./
COPY --from=build go.mod ./
COPY --chown=10001:10001 --chmod=600 pnpm-workspace.yaml ./
COPY ["pnpm-lock.yaml", "./"]
EOF
if [[ "$(root_copy_sources "$fixture_dockerfile" | sort | tr '\n' ' ')" == \
  ".npmrc package.json pnpm-lock.yaml pnpm-workspace.yaml " ]]; then
  pass "the COPY matcher reads continuations, JSON form, and skips --from"
else
  bad "the COPY matcher read '$(root_copy_sources "$fixture_dockerfile" | tr '\n' ' ')': a continued, JSON-form, stage or prefixed source is misparsed"
fi

# The same fixture with every name present in every list: the assertion must
# report nothing. Then drop all but package.json and it must report the rest —
# the control is what proves the failure is the omission, not the fixture.
fixture_workflow="$fixture_dir/workflow.yml"
fixture_filters="$fixture_dir/filters.yml"
write_fixture_lists() {
  {
    printf "on:\n  pull_request:\n    paths:\n"
    printf "      - '%s'\n" "$@"
  } >"$fixture_workflow"
  {
    printf 'docker:\n'
    printf "  - '%s'\n" "$@"
    printf 'console:\n'
    printf "  - '%s'\n" "$@"
  } >"$fixture_filters"
}
write_fixture_lists package.json .npmrc pnpm-workspace.yaml pnpm-lock.yaml
if [[ -z "$(console_trigger_gaps "$fixture_dockerfile" "$fixture_workflow" "$fixture_filters")" ]]; then
  pass "a continued COPY source that every list names is not reported"
else
  bad "the trigger check reports a fully named continued COPY source"
fi
write_fixture_lists package.json
fixture_gaps="$(console_trigger_gaps "$fixture_dockerfile" "$fixture_workflow" "$fixture_filters")"
if grep -Fq '.npmrc does not set run_docker' <<<"$fixture_gaps" &&
  grep -Fq 'pnpm-workspace.yaml does not run the console-quality gate' <<<"$fixture_gaps"; then
  pass "a continued COPY source with no trigger fails the assertion"
else
  bad "the trigger check passed a continued COPY source with no trigger: ${fixture_gaps:-<no gap reported>}"
fi

missing_publish_inputs=()
for service in $publish_services; do
  while read -r input; do
    [[ -n "$input" ]] || continue
    grep -Fq -- "'${input}'" "$DOCKER" ||
      missing_publish_inputs+=("${service}/${input} is not in the Docker Publish PR filter")
  done <<<"$(root_copy_sources "$ROOT/services/${service}/Dockerfile")"
done
if (( ${#missing_publish_inputs[@]} == 0 )); then
  pass "every root file a published image copies is a Docker Publish trigger"
else
  bad "published image inputs with no trigger: ${missing_publish_inputs[*]}"
fi

if (( fail != 0 )); then
  echo "CI tiering policy tests failed" >&2
  exit 1
fi

echo "CI tiering policy tests passed"
