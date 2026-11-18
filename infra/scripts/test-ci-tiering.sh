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

# Every repository-relative source a Dockerfile copies, at any depth. The
# destination is the last token of the instruction (the last element of the
# JSON form), so it is dropped: keeping it was why the first version of this
# matcher only looked at sourceless tokens and could never see a nested source.
#
# Four parsing hazards, all handled here rather than by the caller:
#   * A COPY continued with a trailing backslash is one instruction. Reading only
#     the first line (`COPY package.json \`) missed the second line of sources,
#     so a file copied next to it — the real .npmrc case — could lose its trigger
#     without this test noticing. Continuations are joined before extraction, the
#     way the Dockerfile parser does it.
#   * `COPY --from=<stage>` reads from an earlier stage (or another image), not
#     from the repository, so its sources are not build inputs here and the whole
#     instruction is skipped.
#   * `--chown=` and `--chmod=` are flag tokens, skipped by the same `--` rule
#     without hiding the sources that follow them.
#   * `COPY ["package.json", "./"]` is the JSON form of the same instruction. Its
#     tokens carry brackets, quotes and commas, so no token ever matched a
#     repository file and the whole instruction was skipped.
#   * A bracket expression is Docker pattern syntax, not punctuation. The tokenizer
#     rewrote `[`, `]`, `"` and `,` to spaces, so `COPY services/console/Dockerfil[e]
#     /out/` became two tokens — `services/console/Dockerfil` and `e` — and neither is
#     the file: the wildcard sweep resolved nothing and reported no gap. Words are now
#     split the way the Dockerfile parser splits them (whitespace separates, quotes
#     group, a backslash escapes) and a bracket expression reaches filepath.Match
#     verbatim, where it is a character class.
copy_source_tokens() {
  awk '
    { if (pending != "") { $0 = pending " " $0; pending = "" } }
    /\\[[:space:]]*$/ { sub(/\\[[:space:]]*$/, ""); pending = $0; next }
    { print }
    END { if (pending != "") print pending }
  ' "$1" | awk '
    # Split one instruction body into words the way the Dockerfile parser does:
    # whitespace separates, a quote groups, a backslash escapes the next character,
    # and every other character — `[`, `]` and `,` included — is part of the word.
    # Docker hands the resulting word to filepath.Match, where `[e]` is a class.
    function words_of(s, out,   i, n, c, w, have, quote, k) {
      n = length(s); w = ""; have = 0; quote = ""; k = 0
      for (i = 1; i <= n; i++) {
        c = substr(s, i, 1)
        if (quote != "") {
          if (c == quote) quote = ""
          else w = w c
          have = 1
          continue
        }
        if (c == "\"" || c == "\047") { quote = c; have = 1; continue }
        if (c == "\\" && i < n) { i = i + 1; w = w substr(s, i, 1); have = 1; continue }
        if (c ~ /[[:space:]]/) {
          if (have) { k = k + 1; out[k] = w; w = ""; have = 0 }
          continue
        }
        w = w c; have = 1
      }
      if (have) { k = k + 1; out[k] = w }
      return k
    }
    # The JSON form: only the quoted strings are elements, so the brackets and commas
    # that are syntax never join a source and a class inside a string survives. An
    # element that is not a string is invalid JSON, which Docker rejects; it adds no
    # source here instead of shifting the destination.
    function json_words(s, out,   i, n, c, w, in_string, k) {
      n = length(s); w = ""; in_string = 0; k = 0
      for (i = 1; i <= n; i++) {
        c = substr(s, i, 1)
        if (!in_string) { if (c == "\"") in_string = 1; continue }
        if (c == "\\" && i < n) { i = i + 1; w = w substr(s, i, 1); continue }
        if (c == "\"") { k = k + 1; out[k] = w; w = ""; in_string = 0; continue }
        w = w c
      }
      return k
    }
    # Flags precede the sources, so they are stripped before the remainder is read as
    # the JSON form when it starts with `[`. A `--from` source is another stage or
    # image, not a repository input.
    function strip_flags(s,   f) {
      f = ""
      while (match(s, /^--[^[:space:]]+[[:space:]]+/)) {
        f = f " " substr(s, 1, RLENGTH)
        s = substr(s, RLENGTH + 1)
      }
      FLAGS = f
      return s
    }
    /^COPY([[:space:]]|$)/ {
      rest = $0
      sub(/^COPY[[:space:]]*/, "", rest)
      rest = strip_flags(rest)
      if (FLAGS ~ /--from=/) next
      if (substr(rest, 1, 1) == "[") count = json_words(rest, word)
      else count = words_of(rest, word)
      if (count < 2) next
      for (i = 1; i < count; i++) print word[i]
    }
  '
}

# One COPY token, normalised: relative to the build context, or nothing when it names
# something outside it (an absolute path or a URL).
normalise_copy_source() {
  local source="$1"
  case "$source" in
    /*|*://*) return 0 ;;
  esac
  source="${source#./}"
  case "$source" in
    ''|.) return 0 ;;
  esac
  printf '%s\n' "$source"
}

# Every match of one COPY pattern inside one directory, one per line. Docker applies
# filepath.Match to the directory listing, so a leading dot is not special:
# `COPY config/*.json` copies config/.defaults.json as well as config/settings.json.
# `dotglob` is what makes filename expansion include dotfiles, but `compgen -G` only
# honours it on some Bash versions: measured on 5.3.9 it does, measured on 5.2.15 (the
# CI runner) it emitted only the second file, so a dotfile-only change built a
# different image with no trigger. Pathname expansion is used directly instead:
# `dotglob` is documented to apply to filename expansion on every version. `nullglob`
# makes a pattern that matches nothing emit nothing rather than the literal pattern,
# and an empty IFS keeps a source containing a space in one word. Both options are set
# inside the subshell, so no caller inherits them. `*` and `?` still stop at a `/`, and
# `**` is read as two stars, which is what filepath.Match does with them.
expand_copy_glob() {
  local base="$1" pattern="$2" match
  (
    cd "$base" 2>/dev/null || exit 0
    shopt -s dotglob nullglob
    IFS=
    # shellcheck disable=SC2086 # the pattern is unquoted on purpose: this is the expansion
    for match in $pattern; do
      printf '%s\n' "$match"
    done
  )
}

# The repository files one COPY source stands for, resolved against the build context
# (`context` is repository-relative; `.` is the root every image here builds from).
# A literal source is emitted when it exists. A wildcard source — `COPY *.json /app/`,
# `COPY config/*.yml /etc/` — is a glob in Docker, so the literal path never exists
# and a plain `-e` test emitted nothing: the guard either reported a false gap or
# checked nothing at all, and "no gap" was indistinguishable from "cannot see a gap".
# Every match is emitted instead, and each one is asserted against the v1 filter like
# any other build input.
copy_source_paths() {
  local context="$1" source="$2" prefix='' match
  if [[ "$context" != '.' ]]; then
    prefix="${context%/}/"
  fi
  case "$source" in
    *'*'*|*'?'*|*'['*)
      while IFS= read -r match; do
        [[ -n "$match" ]] || continue
        printf '%s\n' "${prefix}${match#./}"
      done < <(expand_copy_glob "$ROOT/${context}" "$source")
      ;;
    *)
      if [[ -e "$ROOT/${context%/}/${source}" ]]; then
        printf '%s\n' "${prefix}${source}"
      fi
      ;;
  esac
  return 0
}

# Every repository input a Dockerfile's COPY instructions read, one per line.
copy_sources() {
  local dockerfile="$1" context="${2:-.}" token source
  while read -r token; do
    source="$(normalise_copy_source "$token")"
    [[ -n "$source" ]] || continue
    copy_source_paths "$context" "$source"
  done < <(copy_source_tokens "$dockerfile")
}

# Wildcard COPY sources that match nothing. A pattern the tree cannot satisfy is an
# input this guard cannot enumerate, so it is reported by name with the Dockerfile
# that carries it and the build context it was resolved against: an unresolved
# pattern is a hole in the assertion, not a pass, and a diagnostic that names only
# the Dockerfile cannot tell a real gap from a pattern resolved against the wrong
# directory.
copy_pattern_gaps() {
  local dockerfile="$1" context="${2:-.}" token source matches
  while read -r token; do
    source="$(normalise_copy_source "$token")"
    [[ -n "$source" ]] || continue
    case "$source" in
      *'*'*|*'?'*|*'['*) ;;
      *) continue ;;
    esac
    matches="$(copy_source_paths "$context" "$source")"
    [[ -n "$matches" ]] || printf "COPY source '%s' in %s (build context %s) matches no file\n" \
      "$source" "${dockerfile#"$ROOT"/}" "$context"
  done < <(copy_source_tokens "$dockerfile")
  return 0
}

# Root-level files copied into an image (go.mod, .npmrc, …), the subset a filter
# list can name literally: no directory component and a regular file at the
# repository root. Directories are expanded by the profile assertion below.
root_copy_sources() {
  local source
  while read -r source; do
    [[ -n "$source" ]] || continue
    [[ "$source" == */* ]] && continue
    [[ -f "$ROOT/${source}" ]] || continue
    printf '%s\n' "$source"
  done < <(copy_sources "$1")
}

# --- build contexts --------------------------------------------------------
# A COPY source is relative to the image's build context, not to the repository
# root, and one image in this tree does not build from the root: the profile's
# Postgres image builds from infra/compose/v1-single-node/postgres. Resolving every
# Dockerfile against the root made a pattern there match an unrelated root file (a
# false input, silently gated by the wrong trigger) or match nothing at all (a false
# gap, or a wildcard the sweep claims to have checked and did not). The context comes
# from the file that builds the image:
#   1. the profile compose file's `build.context`, which is what `make v1-*` builds;
#   2. docker-publish.yml's `context:`, which is what publishes the image;
#   3. the Dockerfile's own directory, Compose's default for a `build:` directory
#      that names no dockerfile.
# Compose is loaded last so it wins for a Dockerfile both files name. An undeclared
# Dockerfile resolves with (3), and every diagnostic names the context it used, so a
# wrong guess is visible instead of silent.
V1_COMPOSE="$ROOT/infra/compose/v1-single-node/compose.yml"
declare -A dockerfile_contexts=()

# Repository-relative form of the directory `path`, written relative to `base`. Both
# live under ROOT; a path that resolves outside it is not a build context for this
# guard. `cd` is the check that the directory exists and where it really points.
repo_relative() {
  local base="$1" path="$2" resolved
  resolved="$(cd "$base" 2>/dev/null && cd "$path" 2>/dev/null && pwd)" || return 1
  [[ "$resolved" == "$ROOT" || "$resolved" == "$ROOT"/* ]] || return 1
  resolved="${resolved#"$ROOT"}"
  printf '%s\n' "${resolved#/}"
}

# Fold `.` and `..` out of a repository-relative path. A Dockerfile path is a file,
# so it cannot be resolved with `cd`; its context has already been resolved, and the
# rest is string folding.
normalise_relative() {
  local path="$1" segment joined=''
  local -a parts out=()
  IFS='/' read -r -a parts <<<"$path"
  for segment in "${parts[@]}"; do
    case "$segment" in
      ''|.) continue ;;
      ..) (( ${#out[@]} > 0 )) && unset 'out[${#out[@]}-1]'; continue ;;
    esac
    out+=("$segment")
  done
  for segment in "${out[@]}"; do joined+="${segment}/"; done
  printf '%s\n' "${joined%/}"
}

# One `context<TAB>dockerfile` line per `build:` block, with an empty dockerfile when
# the block declares none. Both keys live in the same block, so a `dockerfile:` can
# never be attributed to the service above it.
compose_build_blocks() {
  awk '
    function value(line) {
      sub(/^[^:]*:[[:space:]]*/, "", line)
      sub(/[[:space:]]+#.*$/, "", line)
      sub(/[[:space:]]+$/, "", line)
      gsub(/^"|"$/, "", line)
      return line
    }
    function emit() {
      if (context != "") print context "\t" dockerfile
      context = ""
      dockerfile = ""
      inbuild = 0
    }
    /^[[:space:]]*#/ { next }
    /^[^[:space:]]/ { emit(); next }
    /^  [A-Za-z0-9_.-]+:[[:space:]]*$/ { emit(); next }
    /^[[:space:]]+build:[[:space:]]*[^[:space:]]/ { emit(); context = value($0); emit(); next }
    /^[[:space:]]+build:[[:space:]]*$/ { emit(); inbuild = 1; next }
    inbuild && /^[[:space:]]+context:/ { context = value($0); next }
    inbuild && /^[[:space:]]+dockerfile:/ { dockerfile = value($0); next }
    inbuild && /^[[:space:]]+[A-Za-z0-9_.-]+:/ { emit() }
    END { emit() }
  ' "$1"
}

# The contexts docker-publish.yml builds from. `context:` and `file:` belong to the
# same step, and `file:` is a path inside the context (BuildKit's meaning), so the
# pair is read as a pair.
load_publish_contexts() {
  local context dockerfile context_rel dockerfile_rel
  while IFS=$'\t' read -r context dockerfile; do
    [[ -n "$context" && -n "$dockerfile" ]] || continue
    if ! context_rel="$(repo_relative "$ROOT" "$context")"; then
      printf 'cannot resolve the build context %s declared in %s\n' \
        "$context" "${DOCKER#"$ROOT"/}" >&2
      continue
    fi
    dockerfile_rel="$(normalise_relative "${context_rel}/${dockerfile}")"
    dockerfile_contexts["$dockerfile_rel"]="${context_rel:-.}"
  done < <(awk '
    /^[[:space:]]+context:[[:space:]]*/ {
      sub(/^[[:space:]]+context:[[:space:]]*/, ""); ctx = $0; next
    }
    /^[[:space:]]+file:[[:space:]]*.*Dockerfile[[:space:]]*$/ {
      sub(/^[[:space:]]+file:[[:space:]]*/, ""); sub(/[[:space:]]+$/, ""); print ctx "\t" $0
    }
  ' "$DOCKER")
}

# The contexts the v1 profile builds from. Compose writes `context:` relative to the
# compose file and `dockerfile:` relative to that context, so both are resolved the
# way Compose resolves them; a service with no `dockerfile:` builds
# `<context>/Dockerfile`, which is how the Postgres image is built.
load_profile_contexts() {
  local compose_dir context dockerfile context_rel dockerfile_rel
  compose_dir="$(dirname "$V1_COMPOSE")"
  while IFS=$'\t' read -r context dockerfile; do
    [[ -n "$context" ]] || continue
    if ! context_rel="$(repo_relative "$compose_dir" "$context")"; then
      printf 'cannot resolve the build context %s declared in %s\n' \
        "$context" "${V1_COMPOSE#"$ROOT"/}" >&2
      continue
    fi
    dockerfile_rel="$(normalise_relative "${context_rel}/${dockerfile:-Dockerfile}")"
    dockerfile_contexts["$dockerfile_rel"]="${context_rel:-.}"
  done < <(compose_build_blocks "$V1_COMPOSE")
}

load_publish_contexts
load_profile_contexts

# The key the context map is registered under: a repository-relative Dockerfile path.
# `all_dockerfiles` is relative, while the fixtures below register and call with an
# absolute path, so this is the one place a Dockerfile path is folded to the map's
# spelling. A path outside the repository is left as it is: the map cannot hold a
# meaningful key for it.
dockerfile_key() {
  local dockerfile="$1"
  case "$dockerfile" in
    "$ROOT"/*) printf '%s\n' "${dockerfile#"$ROOT"/}" ;;
    /*) printf '%s\n' "$dockerfile" ;;
    *) normalise_relative "$dockerfile" ;;
  esac
}

# The context one Dockerfile builds from, repository-relative. The lookup and the
# registration both go through dockerfile_key, so the relative and the absolute
# spelling of one Dockerfile cannot resolve differently. Before that, the sweep made
# every path absolute, missed every registered key, fell back to the absolute
# directory, and copy_source_paths prefixed ROOT to it again — so it swept
# $ROOT/$ROOT/... and reported no gap because it examined no directory. An undeclared
# Dockerfile still falls back to its own directory, and the assertion below names it.
dockerfile_context() {
  local key context
  key="$(dockerfile_key "$1")"
  context="${dockerfile_contexts[$key]-}"
  if [[ -n "$context" ]]; then
    printf '%s\n' "$context"
    return 0
  fi
  dirname "$key"
}

# Every Dockerfile the sweep and the coverage assertion reason about.
mapfile -t all_dockerfiles < <(
  find "$ROOT/services" "$ROOT/infra" -name Dockerfile -type f 2>/dev/null |
    sed "s|^$ROOT/||" | sort
)
if (( ${#all_dockerfiles[@]} == 0 )); then
  bad "no Dockerfiles were found under services/ and infra/: the wildcard COPY sweep is broken"
fi

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
# The terminator accepts a digit in the key: the top-level keys are not all
# `^[a-z]+$` — `v1:` is followed by no such key, so a block read that stops on
# `^[a-z]+:$` ran past `v1:` and swallowed it into whichever block came before.
filter_block() {
  local file="$1" key="$2"
  awk -v k="${key}:" '$0 == k { f = 1 } f && /^[a-z0-9_-]+:$/ && $0 != k { exit } f { print }' "$file"
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

# --- wildcard COPY sources resolve against the build context ----------------
# `COPY *.json /app/` names a set of files, not a path. The guard below resolves every
# COPY source, so a pattern is expanded here and each match becomes a build input the
# v1 assertion judges — but a pattern the tree cannot satisfy must be reported, because
# an input this guard cannot enumerate is a hole rather than a pass. The sweep is over
# every Dockerfile in services/ and infra/, not just the profile's, so a wildcard is
# visible wherever it appears, and each Dockerfile's patterns are resolved against the
# context that Dockerfile builds from (see the build-context section above) rather
# than against the repository root.

# A context that is not a directory would make the sweep check nothing, and a map
# that never produces a non-root context would leave the per-image resolution
# untested on the real tree.
context_failures=()
non_root_contexts=()
for dockerfile in "${all_dockerfiles[@]}"; do
  context="$(dockerfile_context "$dockerfile")"
  if [[ ! -d "$ROOT/${context}" ]]; then
    context_failures+=("$dockerfile resolves to ${context}, which is not a directory")
  elif [[ "$context" != '.' ]]; then
    non_root_contexts+=("$dockerfile builds from $context")
  fi
done
if (( ${#context_failures[@]} == 0 )); then
  pass "every one of ${#all_dockerfiles[@]} Dockerfiles resolves to an existing build context"
else
  bad "build contexts that do not exist: ${context_failures[*]}"
fi
if (( ${#non_root_contexts[@]} > 0 )); then
  pass "a non-root build context is resolved per image: ${non_root_contexts[*]}"
else
  bad "no Dockerfile resolved to a non-root context: the context map is not reading the compose file"
fi

# The map is keyed by repository-relative path and the sweep is handed both that form
# and an absolute one. A key that does not agree with the lookup is a silent miss:
# dockerfile_context falls back to dirname, copy_source_paths prefixes ROOT to it, and
# the sweep examines $ROOT/$ROOT/... — a directory that does not exist — reporting no
# gap because it checked nothing. Both spellings are asserted here, in both directions.
context_key_failures=()
for context_key in "${!dockerfile_contexts[@]}"; do
  # A fixture registers an absolute key outside the repository; only an in-repo key
  # has a second spelling to agree with.
  [[ "$context_key" == /* ]] && continue
  context_declared="${dockerfile_contexts[$context_key]}"
  for context_spelling in "$context_key" "$ROOT/$context_key"; do
    context_resolved="$(dockerfile_context "$context_spelling")"
    [[ "$context_resolved" == "$context_declared" ]] ||
      context_key_failures+=("$context_spelling resolves to ${context_resolved}, the map registers ${context_declared}")
  done
done
if (( ${#context_key_failures[@]} == 0 )); then
  pass "every registered Dockerfile resolves to its declared context from either spelling"
else
  bad "a registered Dockerfile resolves to a different context than the map declares: ${context_key_failures[*]}"
fi

# Every Dockerfile the sweep visits must resolve a context that is repository-relative,
# exists, and does not carry the repository root a second time. A registered Dockerfile
# must resolve to the declared context from either spelling; one with no declared build
# path falls back to its own directory and is named here, so the fallback is visible
# instead of silent. This is the assertion the absolute key could not survive: the
# sweep resolved the Postgres image to an absolute directory and every other image to
# $ROOT/<dirname> of a path that was already absolute.
resolved_context_failures=()
undeclared_contexts=()
for dockerfile in "${all_dockerfiles[@]}"; do
  context="$(dockerfile_context "$dockerfile")"
  context_key="$(dockerfile_key "$dockerfile")"
  context_by_absolute="$(dockerfile_context "$ROOT/$dockerfile")"
  if [[ "$context" == /* || "$context" == *"$ROOT"* ]]; then
    resolved_context_failures+=("$dockerfile resolves to ${context}: absolute, or carrying the repository root")
  elif [[ ! -d "$ROOT/${context}" ]]; then
    resolved_context_failures+=("$dockerfile resolves to ${context}, which is not a directory under the repository root")
  elif [[ "$context_by_absolute" != "$context" ]]; then
    resolved_context_failures+=("$dockerfile resolves to ${context} by name and ${context_by_absolute} by absolute path")
  elif [[ -n "${dockerfile_contexts[$context_key]-}" && "$context" != "${dockerfile_contexts[$context_key]}" ]]; then
    resolved_context_failures+=("$dockerfile resolves to ${context}, the map registers ${dockerfile_contexts[$context_key]}")
  elif [[ -z "${dockerfile_contexts[$context_key]-}" ]]; then
    undeclared_contexts+=("$dockerfile (${context})")
  fi
done
if (( ${#resolved_context_failures[@]} == 0 )); then
  pass "the sweep resolves a repository-relative, existing build context for all ${#all_dockerfiles[@]} Dockerfiles"
else
  bad "the sweep does not resolve a usable build context: ${resolved_context_failures[*]}"
fi
if (( ${#undeclared_contexts[@]} > 0 )); then
  pass "Dockerfiles with no declared build path fall back to their own directory: ${undeclared_contexts[*]}"
fi

# Wildcard gaps for a list of Dockerfiles, each resolved against its own build
# context. This is the only place the sweep is wired, so the fixture below drives the
# same call site rather than a copy of it: a sweep that dropped the context would
# resolve every pattern against the root and the fixture would see it. The context is
# resolved from the path as given — dockerfile_context folds it to the map key — and
# only the read path is made absolute, so a caller's spelling cannot change the answer.
sweep_pattern_gaps() {
  local dockerfile context
  for dockerfile in "$@"; do
    context="$(dockerfile_context "$dockerfile")"
    case "$dockerfile" in
      /*) ;;
      *) dockerfile="$ROOT/$dockerfile" ;;
    esac
    copy_pattern_gaps "$dockerfile" "$context"
  done
}
mapfile -t pattern_gap_list < <(sweep_pattern_gaps "${all_dockerfiles[@]}")
if (( ${#pattern_gap_list[@]} == 0 )); then
  pass "every wildcard COPY source across ${#all_dockerfiles[@]} Dockerfiles resolves to at least one file in its own build context"
else
  bad "unresolvable COPY sources: ${pattern_gap_list[*]}"
fi

# The fixture proves both halves the real sweep cannot: a matching pattern contributes
# every match instead of the literal path, and a pattern that matches nothing is named
# with its Dockerfile instead of silently contributing no input.
glob_dockerfile="$fixture_dir/glob.Dockerfile"
cat >"$glob_dockerfile" <<'EOF'
FROM alpine
COPY services/*/Dockerfile /out/
COPY site/package.json ./
EOF
glob_sources="$(copy_sources "$glob_dockerfile")"
if grep -Fxq 'services/console/Dockerfile' <<<"$glob_sources" &&
  grep -Fxq 'services/proxy/Dockerfile' <<<"$glob_sources" &&
  grep -Fxq 'site/package.json' <<<"$glob_sources" &&
  ! grep -Fq '*' <<<"$glob_sources"; then
  pass "a wildcard COPY source expands to every match and a literal source is unchanged"
else
  bad "the COPY resolver read '$(tr '\n' ' ' <<<"$glob_sources")': a wildcard source did not expand to its matches"
fi
if [[ -z "$(copy_pattern_gaps "$glob_dockerfile")" ]]; then
  pass "a wildcard COPY source with matches is not reported as unresolved"
else
  bad "a wildcard COPY source with matches was reported as unresolved: $(copy_pattern_gaps "$glob_dockerfile")"
fi

unmatched_dockerfile="$fixture_dir/unmatched.Dockerfile"
cat >"$unmatched_dockerfile" <<'EOF'
FROM alpine
COPY nowhere/*.json /out/
EOF
unmatched_gaps="$(copy_pattern_gaps "$unmatched_dockerfile")"
if [[ "$unmatched_gaps" == \
  "COPY source 'nowhere/*.json' in ${unmatched_dockerfile#"$ROOT"/} (build context .) matches no file" ]]; then
  pass "a wildcard COPY source that matches nothing is named with its pattern, Dockerfile and context"
else
  bad "an unmatched wildcard COPY source was not reported cleanly: ${unmatched_gaps:-<nothing reported>}"
fi

# A bracket expression is Docker pattern syntax, not punctuation: `COPY
# services/console/Dockerfil[e] /out/` copies services/console/Dockerfile. The
# tokenizer used to rewrite `[`, `]`, `"` and `,` to spaces, so the source became two
# tokens — `services/console/Dockerfil` and `e` — and neither is a file: the sweep
# resolved nothing and reported no gap. Both the shell and the JSON form are checked,
# because each reaches the tokenizer by a different path.
bracket_dockerfile="$fixture_dir/bracket.Dockerfile"
cat >"$bracket_dockerfile" <<'EOF'
FROM alpine
COPY services/console/Dockerfil[e] /out/
COPY ["services/proxy/Dockerfil[e]", "/out/"]
EOF
bracket_sources="$(copy_sources "$bracket_dockerfile")"
if [[ "$(sort <<<"$bracket_sources" | tr '\n' ' ')" == \
  "services/console/Dockerfile services/proxy/Dockerfile " ]]; then
  pass "a bracket expression in a COPY source survives tokenisation and resolves to its file"
else
  bad "a bracket expression in a COPY source was mangled into '$(tr '\n' ' ' <<<"$bracket_sources")'"
fi
if [[ -z "$(copy_pattern_gaps "$bracket_dockerfile")" ]]; then
  pass "a bracket-expression COPY source with a match is not reported as unresolved"
else
  bad "a bracket-expression COPY source was reported as unresolved: $(copy_pattern_gaps "$bracket_dockerfile")"
fi

# Docker applies the pattern to the directory listing, so a leading dot is not
# special: `COPY config/*.json` copies config/.defaults.json as well as
# config/settings.json. `compgen -G` without `dotglob` emitted only the second, which
# is a build input with no trigger. The control below runs the pre-fix expansion on
# the same fixture, so the assertion is known to be about the dotglob and not about
# the fixture. `expand_copy_glob` is the only place the expansion happens;
# `copy_source_paths` delegates to it.
dotfile_dir="$fixture_dir/dotfiles"
mkdir -p "$dotfile_dir/config"
printf '{}\n' >"$dotfile_dir/config/settings.json"
printf '{}\n' >"$dotfile_dir/config/.defaults.json"
dotfile_matches="$(expand_copy_glob "$dotfile_dir" 'config/*.json')"
if [[ "$(sort <<<"$dotfile_matches" | tr '\n' ' ')" == \
  "config/.defaults.json config/settings.json " ]]; then
  pass "a wildcard COPY source expands to a dotfile, as Docker does"
else
  bad "a wildcard COPY source did not expand to a dotfile: '$(tr '\n' ' ' <<<"$dotfile_matches")'"
fi
plain_matches="$( cd "$dotfile_dir" && compgen -G 'config/*.json' || true )"
if [[ "$(grep -c . <<<"$plain_matches")" == 1 ]]; then
  pass "the control shows the pre-fix expansion on that fixture omits the dotfile"
else
  bad "the dotfile control did not reproduce the old behaviour: '$(tr '\n' ' ' <<<"$plain_matches")'"
fi
# Filename expansion replaced `compgen -G`, so the rewrite must not inherit the other
# half of the old behaviour: an unmatched pattern must contribute nothing rather than
# the literal pattern, which would become a false build input. `nullglob` is what
# makes that true, and the control below runs the same expansion without it so the
# assertion is known to be about the option and not about the fixture.
no_match="$(expand_copy_glob "$dotfile_dir" 'absent/*.json')"
plain_no_match="$( cd "$dotfile_dir" && shopt -s dotglob && IFS= && printf '%s\n' absent/*.json )"
if [[ -z "$no_match" && "$plain_no_match" == 'absent/*.json' ]]; then
  pass "a wildcard COPY source that matches nothing expands to nothing, not to the literal pattern"
else
  bad "an unmatched wildcard COPY source expanded to '${no_match:-<nothing>}' (control: '${plain_no_match}')"
fi

# A pattern resolves against the Dockerfile's own build context. The profile's
# Postgres image is the one image in the tree that does not build from the root, so it
# is the case that separates the two readings: against its context, `Dockerfil*`
# matches the Dockerfile and `*.yml` matches nothing; against the root, `Dockerfil*`
# matches nothing (a false gap that would have failed the suite) and `*.yml` matches
# codecov.yml (a false input, silently judged by the wrong trigger).
context_dockerfile="$fixture_dir/context.Dockerfile"
cat >"$context_dockerfile" <<'EOF'
FROM alpine
COPY Dockerfil* /out/
COPY *.yml /etc/
EOF
postgres_context="infra/compose/v1-single-node/postgres"
context_sources="$(copy_sources "$context_dockerfile" "$postgres_context")"
if [[ "$context_sources" == "${postgres_context}/Dockerfile" ]]; then
  pass "a COPY pattern resolves against the image's own build context"
else
  bad "a COPY pattern did not resolve against ${postgres_context}: '$(tr '\n' ' ' <<<"$context_sources")'"
fi
# The fixture Dockerfile is registered with the Postgres context and then run through
# the sweep the real tree uses. A sweep that passed only the Dockerfile would resolve
# both patterns against the root: `Dockerfil*` would be reported as an unmatched
# pattern and `*.yml` would match unrelated root files, so this assertion fails.
dockerfile_contexts["$(dockerfile_key "$context_dockerfile")"]="$postgres_context"
context_gaps="$(sweep_pattern_gaps "$context_dockerfile")"
if [[ "$context_gaps" == \
  "COPY source '*.yml' in ${context_dockerfile#"$ROOT"/} (build context ${postgres_context}) matches no file" ]]; then
  pass "the sweep reports an unmatched pattern with its Dockerfile and the context it used"
else
  bad "the sweep did not report an unmatched pattern with its context: ${context_gaps:-<nothing reported>}"
fi
root_sources="$(copy_sources "$context_dockerfile")"
root_gaps="$(copy_pattern_gaps "$context_dockerfile")"
if grep -Fxq 'codecov.yml' <<<"$root_sources" &&
  ! grep -Fxq "${postgres_context}/Dockerfile" <<<"$root_sources" &&
  grep -Fq "COPY source 'Dockerfil*' in ${context_dockerfile#"$ROOT"/} (build context .) matches no file" <<<"$root_gaps"; then
  pass "the control shows the root context matches unrelated root files and misses the image's own"
else
  bad "the root-context control did not reproduce the old reading: sources '$(tr '\n' ' ' <<<"$root_sources")' gaps '${root_gaps:-<none>}'"
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

# --- every v1 profile image input is a trigger -----------------------------
# Devin, Greptile and CodeRabbit, from three directions: the `v1` filter covered
# the service and package trees but no other file an image copies, so a PR
# changing only infra/provider-capabilities/**, .npmrc or a contract record built
# a different image while run_v1 stayed false. The smoke that proves the profile
# never ran and ci-gate-compose accepted the skip.
#
# The list below is derived from the profile's Dockerfiles instead of being
# written by hand: a hand-written list loses an entry exactly once and then stays
# wrong, which is how the three findings above happened. Every tracked file under
# every copied source is checked, so `COPY packages` covers the whole tree and a
# new nested COPY is caught without touching this file. Each Dockerfile's sources are
# resolved against its own build context, which the section above derived from this
# same compose file.

# Every Dockerfile the profile builds: the ones its compose file names, plus any
# `Dockerfile` beside a build context inside the profile directory (Compose
# defaults to `<context>/Dockerfile`, which is how the postgres image is built).
profile_dockerfiles() {
  {
    grep -oE '^[[:space:]]+dockerfile:[[:space:]]*[^[:space:]]+' "$V1_COMPOSE" |
      sed -E 's/^[[:space:]]+dockerfile:[[:space:]]*//'
    find "$ROOT/infra/compose/v1-single-node" -mindepth 2 -maxdepth 3 \
      -name Dockerfile -type f 2>/dev/null | sed "s|^$ROOT/||"
  } | sed '/^$/d' | sort -u
}

# The repository files a COPY source stands for: the file itself, or every tracked
# file beneath the directory. Tracked only — an untracked scratch file is not a CI
# input — with a filesystem fallback for a checkout without git metadata.
repo_input_files() {
  local source="$1"
  if [[ -f "$ROOT/${source}" ]]; then
    printf '%s\n' "$source"
    return 0
  fi
  [[ -d "$ROOT/${source}" ]] || return 0
  if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "$ROOT" ls-files -z -- "$source" | tr '\0' '\n'
  else
    ( cd "$ROOT/${source}" && find . -type f | sed 's|^\./||' | sed "s|^|${source}/|" )
  fi
}

# Every build input of every profile image, deduplicated. A Dockerfile the compose
# file names but the tree does not have is reported on stderr rather than skipped:
# an unresolvable input is a hole in this assertion, not a pass.
profile_build_inputs() {
  local dockerfile context source
  while read -r dockerfile; do
    [[ -n "$dockerfile" ]] || continue
    if [[ ! -f "$ROOT/${dockerfile}" ]]; then
      printf 'profile Dockerfile %s does not exist\n' "$dockerfile" >&2
      continue
    fi
    context="$(dockerfile_context "$dockerfile")"
    while read -r source; do
      [[ -n "$source" ]] || continue
      repo_input_files "$source"
    done < <(copy_sources "$ROOT/${dockerfile}" "$context")
  done < <(profile_dockerfiles)
}

# dorny/paths-filter matches with picomatch, where `*` and `?` stop at a `/` and
# `**` crosses segments. A bash `case` pattern is not that matcher: in `case`, `*`
# already matches `/`, so collapsing `**` to `*` made the old version accept
# `services/worker/app/x.py` for the pattern `services/*`, which picomatch rejects.
# The guard was looser than the filter it checks, so a real `services/*` entry would
# have passed here while v1-smoke skipped. The translation below is the same one
# .github/scripts/test-evaluate-memory-benchmark-gate.sh uses to check the
# memory_bench filter, kept in step with it for the shapes this file's filters use:
# a literal, `dir/**`, `dir/*.ext`, `**/name.ext`, and a bare `**`.
#
# `**` is globstar only when it is a whole segment, as in picomatch; anywhere else
# it is an ordinary `*`. Path character classes (`[0-9]`) and brace expansion are
# not used in .github/path-filters.yml; adding one needs handling here too.
glob_segment_ere() {
  local seg="$1" out="" i
  for ((i = 0; i < ${#seg}; i++)); do
    case "${seg:i:1}" in
      '*') out+='[^/]*' ;;
      '?') out+='[^/]' ;;
      '.' | '+' | '(' | ')' | '[' | ']' | '{' | '}' | '^' | '$' | '|' | "\\") out+="\\${seg:i:1}" ;;
      *) out+="${seg:i:1}" ;;
    esac
  done
  printf '%s' "$out"
}

glob_to_ere() {
  local pattern="$1" seg i need_sep=0 out=""
  local -a segs
  IFS='/' read -r -a segs <<<"$pattern"
  for ((i = 0; i < ${#segs[@]}; i++)); do
    seg="${segs[i]}"
    if [[ "$seg" == '**' ]]; then
      if (( ${#segs[@]} == 1 )); then
        out+='.+'                        # bare `**`: any path
      elif (( i == 0 )); then
        out+='(.*/)?'                    # `**/x` also matches `x`
      elif (( i + 1 == ${#segs[@]} )); then
        out+='(/.*)?'                    # `dir/**` also matches `dir` itself
      else
        out+='/(.*/)?'                   # `a/**/b` also matches `a/b`
      fi
      need_sep=0
      continue
    fi
    (( need_sep )) && out+='/'
    out+="$(glob_segment_ere "$seg")"
    need_sep=1
  done
  printf '%s' "$out"
}

# The compiled form is cached per pattern: the gap checks below ask the same
# handful of patterns about every build input, and translating one per pair costs
# more than matching the whole list.
declare -A glob_ere_cache=()
glob_matches() {
  local pattern="$1" path="$2" re
  re="${glob_ere_cache["$pattern"]-}"
  if [[ -z "$re" ]]; then
    re="^$(glob_to_ere "$pattern")\$"
    glob_ere_cache["$pattern"]="$re"
  fi
  [[ "$path" =~ $re ]]
}

filter_globs() {
  filter_block "$1" "$2" | sed -nE "s/^  - '(.*)'\$/\\1/p"
}

mapfile -t v1_profile_inputs < <(profile_build_inputs | sort -u)
if (( ${#v1_profile_inputs[@]} == 0 )); then
  bad "no build inputs were derived from the v1 profile images: the derivation is broken"
fi
# The derived build inputs, materialised once: the coverage assertion below reads this
# file, and a mutation control names a fixed inventory through the same function so
# its verdict cannot follow the tree.
v1_inputs_file="$fixture_dir/v1-inputs.txt"
printf '%s\n' "${v1_profile_inputs[@]}" >"$v1_inputs_file"

# Fixture-friendly: the input list defaults to the real one, so a doctored copy of the
# filters file below proves the assertion reports exactly the entry it lost.
v1_input_gaps() {
  local filters="$1" inventory="${2:-$v1_inputs_file}" input pattern blocked
  local -a patterns inputs
  mapfile -t patterns < <(filter_globs "$filters" v1)
  if (( ${#patterns[@]} == 0 )); then
    printf 'the v1 filter declares no patterns\n'
    return 0
  fi
  mapfile -t inputs < <(sed '/^$/d' "$inventory")
  for input in "${inputs[@]}"; do
    [[ -n "$input" ]] || continue
    blocked=1
    for pattern in "${patterns[@]}"; do
      if glob_matches "$pattern" "$input"; then
        blocked=0
        break
      fi
    done
    (( blocked )) && printf '%s is not a v1 trigger\n' "$input"
  done
  return 0
}

# The matcher itself, before it is used to judge the filter: a pattern that cannot
# reach a nested path, or one that matches anything, would make the assertion pass
# for the wrong reason. `want` is the verdict picomatch gives for the pair:
# 0 = the pattern must match, 1 = it must not.
matcher_failures=()
expect_glob() {
  local want="$1" pattern="$2" path="$3" got=1 verdict
  glob_matches "$pattern" "$path" && got=0
  [[ "$got" == "$want" ]] && return 0
  if (( want == 0 )); then verdict='does not match'; else verdict='matches'; fi
  matcher_failures+=("$pattern $verdict $path")
}

expect_glob 0 'infra/compose/v1-single-node/**' 'infra/compose/v1-single-node/postgres/Dockerfile'
expect_glob 0 'services/**' 'services/console/Dockerfile'
expect_glob 0 'infra/scripts/api-*.sh' 'infra/scripts/api-breaking.sh'
expect_glob 1 'services/**' 'infra/provider-capabilities/manifest.v1.json'
expect_glob 1 'infra/scripts/api-*.sh' 'infra/scripts/db-migrate.sh'
# `*` stops at a segment boundary; `**` crosses it. The old matcher could not tell
# this pair apart — it rewrote `**` to `*` and matched with `case`, where `*` already
# matches `/` — so it accepted services/worker/app/x.py for the pattern `services/*`,
# and would have declared the v1 filter complete for an entry a real paths-filter
# run does not match.
expect_glob 1 'services/*' 'services/worker/app/x.py'
expect_glob 0 'services/**' 'services/worker/app/x.py'
# A star in the middle position is one directory, not any depth.
expect_glob 0 'services/*/Dockerfile' 'services/worker/Dockerfile'
expect_glob 1 'services/*/Dockerfile' 'services/a/b/Dockerfile'
# A leading `**/` also matches a path with no directory in front of it: that is how
# the docs filter reaches a root-level markdown file.
expect_glob 0 '**/*.json' 'package.json'
expect_glob 0 '**/*.json' 'engineering/architecture-v2/contracts/deprecations.json'
expect_glob 1 '**/*.json' 'engineering/architecture-v2/contracts/deprecations.yml'

if (( ${#matcher_failures[@]} == 0 )); then
  pass "the filter matcher follows picomatch: literals, one segment per *, any depth per **"
else
  bad "the filter matcher misjudged: ${matcher_failures[*]}"
fi

mapfile -t v1_gaps < <(v1_input_gaps "$FILTERS")
if (( ${#v1_gaps[@]} == 0 )); then
  pass "all ${#v1_profile_inputs[@]} build inputs of the v1 profile images are v1 triggers"
else
  bad "v1 profile image inputs with no trigger: ${v1_gaps[*]}"
fi

# Removing one copied directory from the filter must fail the assertion and name its
# inputs. The exact-equality comparison is the control: a doctored filter that was
# still reported clean would mean the assertion never ran.
#
# This control's inventory is fixed, not derived: the verdict of a mutation must not
# follow whichever files happen to be tracked under that directory, or a file added
# there would rewrite what "naming only its input" means and the control would measure
# the tree instead of the filter. The coverage assertion above still runs the real
# derived inventory, so a new tracked file under a copied directory is still caught.
capability_inventory="$fixture_dir/fixed-provider-capabilities.txt"
printf '%s\n' \
  'infra/provider-capabilities/manifest.v1.json' \
  'infra/provider-capabilities/extra/provider.v2.json' >"$capability_inventory"
v1_fixture_filters="$fixture_dir/v1-filters.yml"
grep -Fv "  - 'infra/provider-capabilities/**'" "$FILTERS" >"$v1_fixture_filters"
expected_capability_gaps="$(printf '%s\n' \
  'infra/provider-capabilities/manifest.v1.json is not a v1 trigger' \
  'infra/provider-capabilities/extra/provider.v2.json is not a v1 trigger')"
if [[ "$(v1_input_gaps "$v1_fixture_filters" "$capability_inventory")" == \
  "$expected_capability_gaps" ]]; then
  pass "dropping a copied directory from the v1 filter fails the assertion, naming only its inputs"
else
  bad "dropping infra/provider-capabilities/** from the v1 filter did not fail the assertion cleanly: $(v1_input_gaps "$v1_fixture_filters" "$capability_inventory")"
fi
grep -Fv "  - 'site/package.json'" "$FILTERS" >"$v1_fixture_filters"
if [[ "$(v1_input_gaps "$v1_fixture_filters")" == 'site/package.json is not a v1 trigger' ]]; then
  pass "dropping a single copied file from the v1 filter fails the assertion, naming only that file"
else
  bad "dropping site/package.json from the v1 filter did not fail the assertion cleanly: $(v1_input_gaps "$v1_fixture_filters")"
fi

# A file reached through a wildcard COPY source is judged by the filter like any other
# input: the input that glob produced must be reported when the pattern covering it is
# dropped, so a pattern that expands to an uncovered file cannot pass as "no gap".
glob_inventory="$fixture_dir/glob-inputs.txt"
glob_fixture_filters="$fixture_dir/glob-filters.yml"
copy_sources "$glob_dockerfile" | grep -Fx 'services/console/Dockerfile' >"$glob_inventory" || true
grep -Fv "  - 'services/**'" "$FILTERS" >"$glob_fixture_filters"
if [[ "$(v1_input_gaps "$glob_fixture_filters" "$glob_inventory")" == \
  'services/console/Dockerfile is not a v1 trigger' ]]; then
  pass "an input reached through a wildcard COPY source is asserted against the v1 filter"
else
  bad "a wildcard-derived input was not checked against the v1 filter: $(v1_input_gaps "$glob_fixture_filters" "$glob_inventory")"
fi

# --- .dockerignore is a build input of every image -------------------------
# Every image in this repository builds from the repository root: `context: .` in
# docker-publish.yml, `../../..` in infra/compose/v1-single-node/compose.yml and in
# infra/compose/bundles/memory-context.yml. Docker reads the .dockerignore at the
# root of that context, so editing it changes what every one of those builds may
# copy. It matched no filter, so a PR editing only this file built a different
# image while run_docker, run_v1 and run_compose all stayed false: the publish
# skipped, and v1-smoke and bundle-smoke reported a skip that the aggregates accept.
# A filter that deliberately keeps it out would have to keep it out of every build
# context as well, which the shared root context does not allow.
image_filters=(docker v1 compose)
dockerignore_gaps() {
  local filters="$1" key pattern covered
  for key in "${image_filters[@]}"; do
    covered=0
    while IFS= read -r pattern; do
      [[ -n "$pattern" ]] || continue
      if glob_matches "$pattern" '.dockerignore'; then
        covered=1
        break
      fi
    done < <(filter_globs "$filters" "$key")
    (( covered )) || printf '.dockerignore is not a %s trigger\n' "$key"
  done
  return 0
}

mapfile -t dockerignore_missing < <(dockerignore_gaps "$FILTERS")
if (( ${#dockerignore_missing[@]} == 0 )); then
  pass ".dockerignore is a trigger for every image build (${image_filters[*]})"
else
  bad "a .dockerignore-only change does not run an image build: ${dockerignore_missing[*]}"
fi

# The control: the same check against a filter with the entry removed must name every
# filter it lost. Without it the assertion above could be passing because the matcher
# matches everything, which is the defect the matcher fixtures guard against.
#
# The control filter is synthetic and carries known patterns, so its verdict cannot
# depend on which patterns the repository's own docker, v1 and compose lists happen to
# hold: a change to the real lists could otherwise make this deletion pass or fail for
# a reason that has nothing to do with the deletion. The check above still runs against
# the real filter; this one proves only that the deletion is visible.
synthetic_image_filters="$fixture_dir/synthetic-image-filters.yml"
cat >"$synthetic_image_filters" <<'EOF'
docker:
  - 'services/**'
  - '.npmrc'
  - '.dockerignore'
v1:
  - 'packages/**'
  - 'go.mod'
  - '.dockerignore'
compose:
  - 'infra/compose/**'
  - '.dockerignore'
EOF
if [[ -z "$(dockerignore_gaps "$synthetic_image_filters")" ]]; then
  pass "the synthetic image filters cover .dockerignore for every image build"
else
  bad "the synthetic image filter control does not cover .dockerignore: $(dockerignore_gaps "$synthetic_image_filters")"
fi
grep -Fv "  - '.dockerignore'" "$synthetic_image_filters" >"$v1_fixture_filters"
dockerignore_dropped="$(dockerignore_gaps "$v1_fixture_filters")"
drop_reported=1
for key in "${image_filters[@]}"; do
  grep -Fxq ".dockerignore is not a ${key} trigger" <<<"$dockerignore_dropped" || drop_reported=0
done
if (( drop_reported )); then
  pass "dropping .dockerignore fails the trigger check for each of the ${#image_filters[@]} image builds"
else
  bad "dropping .dockerignore did not fail the trigger check cleanly: ${dockerignore_dropped:-<nothing reported>}"
fi

# --- declared vs live required contexts ------------------------------------
# P1-25: check-required-ci-gates.sh compares .github/branch-protection-main.json to
# the rule GitHub actually enforces. That rule is not readable without repository
# admin, so the comparison is driven through IBEX_LIVE_REQUIRED_CONTEXTS here: an
# assertion nobody has seen fail is not known to work.
REQUIRED_GATES="$ROOT/.github/scripts/check-required-ci-gates.sh"
mapfile -t declared_contexts < <(
  jq -r '.required_status_checks.checks[].context' "$ROOT/.github/branch-protection-main.json"
)
declared_list="$(IFS=,; printf '%s' "${declared_contexts[*]}")"
if IBEX_LIVE_REQUIRED_CONTEXTS="$declared_list" bash "$REQUIRED_GATES" >/dev/null 2>&1; then
  pass "the live-context comparison passes when every declared context is enforced"
else
  bad "the live-context comparison fails when every declared context is enforced"
fi

# The five contexts the live rule enforced when this row was written. The four
# missing ones must be named, or the failure does not say what to apply.
enforced_subset="gitleaks,semantic-pr-title,ci-gate-repo,ci-gate-go,ci-gate-security"
gate_rc=0
gate_out="$(IBEX_LIVE_REQUIRED_CONTEXTS="$enforced_subset" bash "$REQUIRED_GATES" 2>&1)" || gate_rc=$?
# Read the failure line itself: the structural output prints every declared context,
# so a bare grep for a name would match a passing run too.
unenforced_line="$(grep -F 'Declared but NOT enforced by the live main branch rule:' <<<"$gate_out" || true)"
if (( gate_rc == 0 )); then
  bad "the live-context comparison passed a declared context the live rule does not enforce"
elif [[ -z "$unenforced_line" ]]; then
  bad "the live-context comparison failed without naming the unenforced contexts: $gate_out"
else
  missing_names=0
  for context in ci-gate-site ci-gate-python ci-gate-memory-benchmark ci-gate-semgrep; do
    grep -Fq "$context" <<<"$unenforced_line" || missing_names=1
  done
  if (( missing_names == 0 )); then
    pass "the live-context comparison fails and names every declared-but-unenforced context"
  else
    bad "the live-context comparison did not name every missing context: $unenforced_line"
  fi
fi

# A readable live rule that reports zero checks is a successful read of an empty
# list, not an unreadable rule. The old `&& [[ -n "$live" ]]` normalised it away,
# printed "could not read" and exited 0 while every declared context was
# unenforced; the two facts need different exits.
empty_rc=0
empty_out="$(IBEX_LIVE_REQUIRED_CONTEXTS="," bash "$REQUIRED_GATES" 2>&1)" || empty_rc=$?
empty_line="$(grep -F 'Declared but NOT enforced by the live main branch rule:' <<<"$empty_out" || true)"
empty_unnamed=0
for context in "${declared_contexts[@]}"; do
  grep -Fq "$context" <<<"$empty_line" || empty_unnamed=1
done
if (( empty_rc != 0 )) && (( empty_unnamed == 0 )); then
  pass "a readable live rule with zero checks fails and names all ${#declared_contexts[@]} declared contexts"
else
  bad "a readable live rule with zero checks reported success (exit ${empty_rc}) or did not name every declared context: ${empty_out:-<no output>}"
fi

# The comparison is only as good as the read behind it, and IBEX_LIVE_REQUIRED_CONTEXTS
# bypasses the read. These cases drive `gh` itself. A response that carries no enforced
# context at all is a successful read of zero checks and must fail; a response that
# names a context the read can see must not turn it into a false "unenforced"; and a
# failed request is the one case that stays a warning, because it is genuinely "could
# not read".
gate_bin="$fixture_dir/gate-bin"
mkdir -p "$gate_bin"
cat >"$gate_bin/gh" <<'GATE_STUB'
#!/usr/bin/env bash
# Stand-in for `gh api <path> --jq <expr>`: applies expr to the protection JSON the
# case points at, and fails when jq cannot evaluate it, which is what gh does.
# GH_STUB_RC makes the request itself fail (a non-200, an absent token).
set -euo pipefail
[[ "${1:-}" == "api" ]] || exit 1
if [[ -n "${GH_STUB_RC:-}" ]]; then
  exit "${GH_STUB_RC}"
fi
expr=""
while (( $# )); do
  case "$1" in
    --jq) expr="$2"; shift 2 ;;
    *) shift ;;
  esac
done
jq -r "$expr" "${GH_STUB_PROTECTION:?}" || exit 1
GATE_STUB
chmod +x "$gate_bin/gh"

gate_rc=0
gate_out=""
run_live_gate() {
  local protection="$1" fail="${2:-}"
  local -a env_args=(
    -u IBEX_LIVE_REQUIRED_CONTEXTS -u GITHUB_STEP_SUMMARY
    PATH="$gate_bin:$PATH"
    GITHUB_REPOSITORY=owner/repo
    GH_STUB_PROTECTION="$protection"
  )
  [[ -n "$fail" ]] && env_args+=(GH_STUB_RC="$fail")
  gate_rc=0
  gate_out="$(env "${env_args[@]}" bash "$REQUIRED_GATES" 2>&1)" || gate_rc=$?
}

# Every declared context must be named by the failure, not just some of them.
names_every_declared_context() {
  local line context
  line="$(grep -F 'Declared but NOT enforced by the live main branch rule:' <<<"$1" || true)"
  [[ -n "$line" ]] || return 1
  for context in "${declared_contexts[@]}"; do
    grep -Fq "$context" <<<"$line" || return 1
  done
}

# The live main rule publishes the same contexts twice, under `contexts` and under
# `checks` (verified against the API), so the read must de-duplicate: applied to a
# response that carries both keys with the same list, the guard's own expression must
# name every context exactly once. The expression is taken from the script rather than
# copied here, so this assertion follows the read that actually ships. De-duplication is
# all this fixture can prove — both keys hold the same list, so an expression that read
# either key alone would pass it too. The next fixture is the one that proves the union.
live_jq_expression="$(sed -n "s/^[[:space:]]*--jq '\(.*\)'.*$/\1/p" "$REQUIRED_GATES" | head -1)"
protection_both_keys="$fixture_dir/protection-both-keys.json"
declared_json="$(printf '%s\n' "${declared_contexts[@]}" | jq -R . | jq -s .)"
jq -n --argjson c "$declared_json" \
  '{required_status_checks: {strict: true, contexts: $c, checks: ($c | map({context: .}))}}' \
  >"$protection_both_keys"
read_contexts="$(jq -r "$live_jq_expression" "$protection_both_keys" 2>&1)"
if [[ -n "$live_jq_expression" ]] &&
  [[ "$(sort <<<"$read_contexts")" == "$(printf '%s\n' "${declared_contexts[@]}" | sort)" ]]; then
  pass "the live read de-duplicates a rule that carries the same contexts under both keys"
else
  bad "the live read did not de-duplicate the same contexts under both keys: [${read_contexts}]"
fi

# A union needs a fixture whose two shapes hold different contexts. Each declared
# context is placed in exactly one of them, so an expression that reads only `contexts`
# or only `checks` cannot produce the full set and only a read of both can.
contexts_only=()
checks_only=()
for i in "${!declared_contexts[@]}"; do
  if (( i % 2 == 0 )); then
    contexts_only+=("${declared_contexts[i]}")
  else
    checks_only+=("${declared_contexts[i]}")
  fi
done
protection_split="$fixture_dir/protection-split-keys.json"
jq -n \
  --argjson c "$(printf '%s\n' "${contexts_only[@]}" | jq -R . | jq -s .)" \
  --argjson k "$(printf '%s\n' "${checks_only[@]}" | jq -R . | jq -s 'map({context: .})')" \
  '{required_status_checks: {strict: true, contexts: $c, checks: $k}}' \
  >"$protection_split"
split_contexts="$(jq -r "$live_jq_expression" "$protection_split" 2>&1)"
if (( ${#contexts_only[@]} > 0 && ${#checks_only[@]} > 0 )) &&
  [[ -n "$live_jq_expression" ]] &&
  [[ "$(sort <<<"$split_contexts")" == "$(printf '%s\n' "${declared_contexts[@]}" | sort)" ]]; then
  pass "the live read takes the union of contexts and checks when the two shapes differ"
else
  bad "the live read did not take the union of two shapes that differ: [${split_contexts}]"
fi

# The two single-field expressions the union replaces. On this fixture each loses the
# contexts that live only in the shape it does not read, which is what makes the union
# assertion above bite: with the old same-list fixture both of these produced the full
# set and passed.
contexts_field_read="$(jq -r \
  '[(.required_status_checks.contexts // [])[]] | map(select(. != null and . != "")) | unique | .[]' \
  "$protection_split")"
checks_field_read="$(jq -r \
  '[(.required_status_checks.checks // [])[].context] | map(select(. != null and . != "")) | unique | .[]' \
  "$protection_split")"
if [[ "$(sort <<<"$contexts_field_read")" == "$(printf '%s\n' "${contexts_only[@]}" | sort)" ]] &&
  [[ "$(sort <<<"$checks_field_read")" == "$(printf '%s\n' "${checks_only[@]}" | sort)" ]] &&
  [[ "$(sort <<<"$contexts_field_read")" != "$(sort <<<"$split_contexts")" ]] &&
  [[ "$(sort <<<"$checks_field_read")" != "$(sort <<<"$split_contexts")" ]]; then
  pass "a read of one context shape alone misses the other's contexts, so only the union passes"
else
  bad "a one-field expression produced the union read on a fixture whose keys hold different contexts"
fi

# The gate itself reports both: every declared context is enforced by the split rule,
# including the one that exists only under `contexts` and the one that exists only
# under `checks`.
run_live_gate "$protection_split"
if (( gate_rc == 0 )) && grep -Fq 'are enforced by the live main rule' <<<"$gate_out"; then
  pass "contexts that appear in only one of the two shapes are both reported enforced"
else
  bad "a live rule that splits the contexts across both shapes did not pass (exit ${gate_rc}): ${gate_out:-<no output>}"
fi

# The control: remove the context that lives only under `contexts` and the one that
# lives only under `checks`. The gate must name both, which is what "reported enforced"
# means for a context that has no duplicate in the other shape.
split_control_context="${contexts_only[0]:-}"
split_control_check="${checks_only[0]:-}"
if [[ -n "$split_control_context" && -n "$split_control_check" ]]; then
  protection_split_missing="$fixture_dir/protection-split-missing.json"
  jq --arg drop_contexts "$split_control_context" --arg drop_checks "$split_control_check" \
    '.required_status_checks.contexts -= [$drop_contexts]
     | .required_status_checks.checks -= [{"context": $drop_checks}]' \
    "$protection_split" >"$protection_split_missing"
  run_live_gate "$protection_split_missing"
  split_missing_line="$(grep -F 'Declared but NOT enforced by the live main branch rule:' <<<"$gate_out" || true)"
  if (( gate_rc != 0 )) &&
    grep -Fq "$split_control_context" <<<"$split_missing_line" &&
    grep -Fq "$split_control_check" <<<"$split_missing_line"; then
    pass "a context removed from the only shape that carried it is reported unenforced"
  else
    bad "a context removed from its only shape was not reported unenforced (exit ${gate_rc}): ${gate_out:-<no output>}"
  fi
else
  bad "the declared inventory has fewer than two contexts, so the union of the two shapes cannot be proven"
fi

# 0. The same read on a rule that enforces everything must pass: the control for the
#    cases below, and the only one of them that runs the happy path.
protection_full="$fixture_dir/protection-full.json"
printf '%s\n' "${declared_contexts[@]}" |
  jq -R . | jq -s '{required_status_checks: {strict: true, contexts: .}}' >"$protection_full"
run_live_gate "$protection_full"
if (( gate_rc == 0 )) && grep -Fq 'are enforced by the live main rule' <<<"$gate_out"; then
  pass "a readable live rule that enforces every declared context passes"
else
  bad "a readable live rule that enforces every declared context did not pass (exit ${gate_rc}): ${gate_out:-<no output>}"
fi

# 1. `checks` and no `contexts`: the newer shape, which the checked-in rule file itself
#    uses. Reading `contexts` alone read zero from this response and reported every
#    declared context as unenforced — a false alarm. The context the response names is
#    enforced, and every other one is still named.
protection_checks="$fixture_dir/protection-checks-only.json"
printf '%s\n' '{"required_status_checks": {"strict": true, "checks": [{"context": "gitleaks"}]}}' \
  >"$protection_checks"
run_live_gate "$protection_checks"
checks_line="$(grep -F 'Declared but NOT enforced by the live main branch rule:' <<<"$gate_out" || true)"
checks_unnamed=0
for context in "${declared_contexts[@]}"; do
  [[ "$context" == gitleaks ]] && continue
  grep -Fq "$context" <<<"$checks_line" || checks_unnamed=1
done
if (( gate_rc != 0 )) && [[ -n "$checks_line" ]] &&
  ! grep -Fq 'gitleaks' <<<"$checks_line" && (( checks_unnamed == 0 )); then
  pass "a live rule that carries only checks reads the context it names as enforced"
else
  bad "a checks-only live rule reported success (exit ${gate_rc}), treated its context as unenforced, or lost one: ${gate_out:-<no output>}"
fi

# 2. Both keys present and empty: a readable rule that enforces nothing. A successful
#    read of zero checks must fail and name every declared context, not print the
#    "could not read" warning and exit 0.
protection_zero="$fixture_dir/protection-zero-checks.json"
printf '%s\n' '{"required_status_checks": {"strict": true, "contexts": [], "checks": []}}' \
  >"$protection_zero"
run_live_gate "$protection_zero"
if (( gate_rc != 0 )) && names_every_declared_context "$gate_out"; then
  pass "a live response with both context shapes empty fails and names all ${#declared_contexts[@]} declared contexts"
else
  bad "a live response with both context shapes empty reported success (exit ${gate_rc}) or did not name every declared context: ${gate_out:-<no output>}"
fi

# 3. The whole block is null: a rule configured with no required checks at all.
protection_null="$fixture_dir/protection-null.json"
printf '%s\n' '{"required_status_checks": null}' >"$protection_null"
run_live_gate "$protection_null"
if (( gate_rc != 0 )) && names_every_declared_context "$gate_out"; then
  pass "a live rule with a null required_status_checks fails and names every declared context"
else
  bad "a live rule with a null required_status_checks reported success (exit ${gate_rc}) or did not name every declared context: ${gate_out:-<no output>}"
fi

# 4. The request itself fails, which is "could not read" and stays a warning: the
#    script has no evidence either way, and failing would make the job unpassable
#    without a repository-admin token.
run_live_gate "$protection_full" 22
if (( gate_rc == 0 )) &&
  grep -Fq 'not readable with this credential' <<<"$gate_out" &&
  ! grep -Fq 'Declared but NOT enforced' <<<"$gate_out"; then
  pass "a failed protection read warns and exits 0 instead of reporting an unenforced context"
else
  bad "a failed protection read did not take the warning path (exit ${gate_rc}): ${gate_out:-<no output>}"
fi

# A different context that embeds a declared name is not that context. The old
# comparison asked whether the joined list contained " $context ", so
# "legacy ci-gate-site" read as enforcing "ci-gate-site". The exact failure line is
# asserted, because naming the wrong context is the same defect reversed.
embedded_list=""
for context in "${declared_contexts[@]}"; do
  if [[ "$context" == "ci-gate-site" ]]; then
    embedded_list+="legacy ci-gate-site,"
  else
    embedded_list+="${context},"
  fi
done
embedded_rc=0
embedded_out="$(IBEX_LIVE_REQUIRED_CONTEXTS="$embedded_list" bash "$REQUIRED_GATES" 2>&1)" || embedded_rc=$?
embedded_line="$(grep -F 'Declared but NOT enforced by the live main branch rule:' <<<"$embedded_out" || true)"
if (( embedded_rc != 0 )) &&
  [[ "$embedded_line" == 'Declared but NOT enforced by the live main branch rule: ci-gate-site' ]]; then
  pass "a live context that only embeds a declared name does not count as enforcing it"
else
  bad "a live context that embeds a declared name counted as enforcing it (exit ${embedded_rc}): ${embedded_out:-<no output>}"
fi

# --- the release manifest waits for the smoke evidence it needs ------------
# `gh run list` does not report a run that is still in progress, and release-docker.yml
# and ci.yml both start from the release merge with no dependency edge. A single
# lookup therefore recorded `unverified` for a bundle whose artifact was uploaded
# moments later. The step body is executed here against a `gh` stub: a completed run
# must promote, a run that is still in progress must be waited for and then promote,
# and an absent, stalled or failed run must stay `unverified` without pretending
# otherwise.
step_run_body() {
  awk -v want="      - name: $2" '
    $0 == want { found = 1; next }
    found && /^      - name:/ { exit }
    found && /^        run: \|$/ { body = 1; next }
    body && /^          / { sub(/^          /, ""); print; next }
    body && /^[[:space:]]*$/ { print ""; next }
    body { exit }
  ' "$1"
}

smoke_fetch="$fixture_dir/fetch-bundle-smoke.sh"
step_run_body "$release_docker" "Fetch the bundle smoke result for this commit" >"$smoke_fetch"
if [[ -s "$smoke_fetch" ]] && bash -n "$smoke_fetch"; then
  pass "the release smoke-fetch step body is extractable and parses"
else
  bad "the release smoke-fetch step body could not be extracted from release-docker.yml"
fi

stub_dir="$fixture_dir/bin"
mkdir -p "$stub_dir"
# Minimal gh stand-in. `run list` replays run-list.N.json when the case provides a
# sequence (the race case) and run-list.json otherwise; `run download` writes the
# artifact the real step would download.
cat >"$stub_dir/gh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
state="${GH_STUB_DIR:?GH_STUB_DIR is required}"
printf '%s\n' "$*" >>"$state/calls.log"
case "$1 $2" in
  "run list")
    n="$(grep -c '^run list' "$state/calls.log" || true)"
    if [[ -f "$state/run-list.${n}.json" ]]; then
      cat "$state/run-list.${n}.json"
    else
      cat "$state/run-list.json"
    fi
    ;;
  "run download")
    if [[ -f "$state/no-artifact" ]]; then
      exit 1
    fi
    shift 2
    dir=""
    while (( $# )); do
      case "$1" in
        --dir) dir="$2"; shift 2 ;;
        --name|--repo) shift 2 ;;
        *) shift ;;
      esac
    done
    mkdir -p "$dir"
    printf '{"status":"passed","commit":"%s","finished_at":"2026-11-18T00:00:00Z"}\n' \
      "${GH_STUB_COMMIT:-}" >"$dir/bundle-smoke-result.json"
    ;;
  *) exit 1 ;;
esac
STUB
chmod +x "$stub_dir/gh"

smoke_sha="0123456789abcdef0123456789abcdef01234567"
run_smoke_case() {
  local name="$1" attempts="${2:-3}"
  local case_dir="$fixture_dir/smoke-${name}"
  mkdir -p "$case_dir"
  : >"$case_dir/calls.log"
  : >"$case_dir/github-output"
  local rc=0
  (
    cd "$case_dir" || exit 1
    PATH="$stub_dir:$PATH" GH_STUB_DIR="$case_dir" GH_STUB_COMMIT="$smoke_sha" \
      COMMIT="$smoke_sha" REPOSITORY=owner/repo GH_TOKEN=stub \
      GITHUB_OUTPUT="$case_dir/github-output" \
      IBEX_SMOKE_RUN_ATTEMPTS="$attempts" IBEX_SMOKE_RUN_INTERVAL=0 \
      bash "$smoke_fetch"
  ) >"$case_dir/stdout" 2>"$case_dir/stderr" || rc=$?
  printf '%s' "$rc"
}

completed_run="[{\"databaseId\":4242,\"headSha\":\"${smoke_sha}\",\"status\":\"completed\",\"conclusion\":\"success\"}]"
in_progress_run="[{\"databaseId\":4243,\"headSha\":\"${smoke_sha}\",\"status\":\"in_progress\",\"conclusion\":null}]"

mkdir -p "$fixture_dir/smoke-completed"
printf '%s\n' "$completed_run" >"$fixture_dir/smoke-completed/run-list.json"
smoke_rc="$(run_smoke_case completed)"
if [[ "$smoke_rc" == 0 ]] &&
  grep -Fq 'smoke_results=smoke-results/bundle-smoke-result.json' \
    "$fixture_dir/smoke-completed/github-output" &&
  [[ -f "$fixture_dir/smoke-completed/smoke-results/bundle-smoke-result.json" ]]; then
  pass "a completed CI run for the commit promotes its bundle smoke evidence"
else
  bad "a completed CI run did not promote its bundle smoke evidence (exit ${smoke_rc})"
fi

# The race this change fixes: the first lookup sees the run in progress, a later one
# sees it completed. The old single-shot lookup recorded unverified here.
mkdir -p "$fixture_dir/smoke-race"
printf '%s\n' "$in_progress_run" >"$fixture_dir/smoke-race/run-list.1.json"
printf '%s\n' "$completed_run" >"$fixture_dir/smoke-race/run-list.json"
smoke_rc="$(run_smoke_case race)"
if [[ "$smoke_rc" == 0 ]] &&
  grep -Fq 'smoke_results=smoke-results/bundle-smoke-result.json' \
    "$fixture_dir/smoke-race/github-output"; then
  pass "a run that is still in progress is waited for and promotes once it completes"
else
  bad "a run that was in progress when the release looked did not promote after completing (exit ${smoke_rc})"
fi

# In progress for the whole bound: the wait ends, nothing is promoted, and no
# artifact is invented.
mkdir -p "$fixture_dir/smoke-stalled"
printf '%s\n' "$in_progress_run" >"$fixture_dir/smoke-stalled/run-list.json"
smoke_rc="$(run_smoke_case stalled 3)"
if [[ "$smoke_rc" == 0 ]] &&
  [[ ! -s "$fixture_dir/smoke-stalled/github-output" ]] &&
  grep -Fq 'did not complete within' "$fixture_dir/smoke-stalled/stdout" &&
  ! grep -Fq 'run download' "$fixture_dir/smoke-stalled/calls.log"; then
  pass "a run that never completes stops at the bound and stays unverified"
else
  bad "a run that never completes did not stop at the bound: $(cat "$fixture_dir/smoke-stalled/stdout")"
fi

# Absent: no run exists for the commit at all. It must give up early (three checks),
# keep unverified, and say which fact it found.
mkdir -p "$fixture_dir/smoke-absent"
printf '%s\n' '[]' >"$fixture_dir/smoke-absent/run-list.json"
smoke_rc="$(run_smoke_case absent 24)"
if [[ "$smoke_rc" == 0 ]] &&
  [[ ! -s "$fixture_dir/smoke-absent/github-output" ]] &&
  grep -Fq 'no CI push run on main for' "$fixture_dir/smoke-absent/stdout" &&
  [[ "$(grep -c 'run list' "$fixture_dir/smoke-absent/calls.log")" == 3 ]]; then
  pass "an absent CI run stops after three checks instead of burning the whole bound"
else
  bad "an absent CI run did not stop early: $(cat "$fixture_dir/smoke-absent/stdout")"
fi

# A completed but red run: the artifact may exist, but a failed run is not evidence.
mkdir -p "$fixture_dir/smoke-failed"
printf '%s\n' "[{\"databaseId\":4244,\"headSha\":\"${smoke_sha}\",\"status\":\"completed\",\"conclusion\":\"failure\"}]" \
  >"$fixture_dir/smoke-failed/run-list.json"
smoke_rc="$(run_smoke_case failed)"
if [[ "$smoke_rc" == 0 ]] &&
  [[ ! -s "$fixture_dir/smoke-failed/github-output" ]] &&
  grep -Fq 'is not evidence' "$fixture_dir/smoke-failed/stdout" &&
  ! grep -Fq 'run download' "$fixture_dir/smoke-failed/calls.log"; then
  pass "a failed CI run leaves the bundle unverified instead of promoting its artifact"
else
  bad "a failed CI run was treated as smoke evidence: $(cat "$fixture_dir/smoke-failed/stdout")"
fi

if (( fail != 0 )); then
  echo "CI tiering policy tests failed" >&2
  exit 1
fi

echo "CI tiering policy tests passed"
