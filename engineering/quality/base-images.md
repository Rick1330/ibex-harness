# Base images — recorded pins

Every `FROM` in this repository pins a digest. This file records **what each digest is, when it was pinned, and what
the build therefore inherits**, so that a base refresh is a reviewable change instead of an opaque one-line edit.

This is a record, not a policy. `DEPENDENCIES.md` §10 states which images are preferred; where the two disagree, this
file describes what actually ships and the disagreement is a defect to fix, not a choice to make.

## Scope and provenance

- **13 Dockerfiles, 33 `FROM` lines, 8 distinct images**, counted from the tree with the command in
  [Regenerating](#regenerating).
- The Dockerfiles reference images by digest only (`python@sha256:…`), so the **tag** column cannot be read from the
  Dockerfile. It is the digest's `org.opencontainers.image.version` annotation in the registry, which is how the
  upstream publisher names the tag that produces that digest.
- **Pinned** is the date the digest entered that particular file on `origin/main`
  (`git log -1 --format=%ad -S<digest> -- <file>`). The same digest can show different dates in different files
  because the file itself was added later.
- **Base built** is the `org.opencontainers.image.created` timestamp of the manifest's `amd64` entry
  (`podman manifest inspect`). `pgvector/pgvector` publishes no annotations, so its date comes from the image config
  and its version was read from the image (`vector.control` `default_version = 0.8.6`, `PG_MAJOR=16`).

## Distinct base images

| Image | Digest | Base built | First pinned in the tree |
|---|---|---|---|
| `alpine:3.24.1` | `sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b` | 2026-06-16 | 2026-09-19 |
| `alpine:3.24.2` | `sha256:f59abe656b692d901e184be3445e084786602108599d2a51d229c0f5a48c71bf` | 2026-09-17 | 2026-11-20 |
| `alpine:3.24.2` (superseded) | `sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6` | 2026-09-17 | 2026-09-23 |
| `ghcr.io/astral-sh/uv:0.7.20` | `sha256:2fd1b38e3398a256d6af3f71f0e2ba6a517b249998726a64d8cfbe55ab34af5e` | 2025-07-09 | 2026-08-25 |
| `golang:1.26.11-alpine3.24` | `sha256:ae52b5bc6ed045a9ed26ab03dc19327a802a9cc9aa8b27ed57f5c6b60579b0bb` | 2026-11-10 | 2026-11-11 |
| `node:22-bookworm-slim` | `sha256:5ec23b7c622b00547753bc6ffd78085dd868a68aeb41c8e0a1418f033e13d96d` | 2026-11-05 | 2026-11-07 |
| `pgvector/pgvector:0.8.6-pg16` | `sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b` | 2026-08-13 | 2026-11-14 |
| `python:3.12-slim-bookworm` | `sha256:da54eb86849fe19be7584d8b3f291fcf0c53c196760ab3d70dc6382f681ef9c0` | 2026-11-05 | 2026-11-05 |
| `python:3.13-slim-bookworm` | `sha256:413041be39649714885528a06586416279db85744b6dcdf290af0ae557d782f6` | 2026-11-05 | 2026-11-05 |

## Every `FROM` in the tree

| Dockerfile | Stage | Image | Digest | Pinned |
|---|---|---|---|---|
| `infra/compose/v1-single-node/postgres/Dockerfile` | final | `pgvector/pgvector:0.8.6-pg16` | `sha256:ccc6e83d6e35…` | 2026-11-14 |
| `infra/migrations/Dockerfile` | build | `golang:1.26.11-alpine3.24` | `sha256:ae52b5bc6ed0…` | 2026-11-11 |
| `infra/migrations/Dockerfile` | final | `alpine:3.24.1` | `sha256:28bd5fe8b56d…` | 2026-09-19 |
| `services/api/Dockerfile` | uv | `ghcr.io/astral-sh/uv:0.7.20` | `sha256:2fd1b38e3398…` | 2026-09-09 |
| `services/api/Dockerfile` | deps | `python:3.12-slim-bookworm` | `sha256:da54eb86849f…` | 2026-11-05 |
| `services/api/Dockerfile` | runtime | `python:3.12-slim-bookworm` | `sha256:da54eb86849f…` | 2026-11-05 |
| `services/auth/Dockerfile` | build | `golang:1.26.11-alpine3.24` | `sha256:ae52b5bc6ed0…` | 2026-11-11 |
| `services/auth/Dockerfile` | final | `alpine:3.24.2` | `sha256:f59abe656b69…` | 2026-11-20 |
| `services/console/Dockerfile` | build | `node:22-bookworm-slim` | `sha256:5ec23b7c622b…` | 2026-11-07 |
| `services/console/Dockerfile` | runtime | `node:22-bookworm-slim` | `sha256:5ec23b7c622b…` | 2026-11-07 |
| `services/context/Dockerfile` | uv | `ghcr.io/astral-sh/uv:0.7.20` | `sha256:2fd1b38e3398…` | 2026-11-07 |
| `services/context/Dockerfile` | stubs | `python:3.12-slim-bookworm` | `sha256:da54eb86849f…` | 2026-11-07 |
| `services/context/Dockerfile` | deps | `python:3.12-slim-bookworm` | `sha256:da54eb86849f…` | 2026-11-07 |
| `services/context/Dockerfile` | runtime | `python:3.12-slim-bookworm` | `sha256:da54eb86849f…` | 2026-11-07 |
| `services/embedder/Dockerfile` | uv | `ghcr.io/astral-sh/uv:0.7.20` | `sha256:2fd1b38e3398…` | 2026-08-25 |
| `services/embedder/Dockerfile` | deps | `python:3.12-slim-bookworm` | `sha256:da54eb86849f…` | 2026-11-05 |
| `services/embedder/Dockerfile` | runtime | `python:3.12-slim-bookworm` | `sha256:da54eb86849f…` | 2026-11-05 |
| `services/mcp-memory/Dockerfile` | uv | `ghcr.io/astral-sh/uv:0.7.20` | `sha256:2fd1b38e3398…` | 2026-08-25 |
| `services/mcp-memory/Dockerfile` | deps | `python:3.13-slim-bookworm` | `sha256:413041be3964…` | 2026-11-05 |
| `services/mcp-memory/Dockerfile` | runtime | `python:3.13-slim-bookworm` | `sha256:413041be3964…` | 2026-11-05 |
| `services/mcp-operator/Dockerfile` | uv | `ghcr.io/astral-sh/uv:0.7.20` | `sha256:2fd1b38e3398…` | 2026-10-20 |
| `services/mcp-operator/Dockerfile` | deps | `python:3.13-slim-bookworm` | `sha256:413041be3964…` | 2026-11-05 |
| `services/mcp-operator/Dockerfile` | runtime | `python:3.13-slim-bookworm` | `sha256:413041be3964…` | 2026-11-05 |
| `services/memory/Dockerfile` | uv | `ghcr.io/astral-sh/uv:0.7.20` | `sha256:2fd1b38e3398…` | 2026-08-26 |
| `services/memory/Dockerfile` | deps | `python:3.12-slim-bookworm` | `sha256:da54eb86849f…` | 2026-11-05 |
| `services/memory/Dockerfile` | runtime | `python:3.12-slim-bookworm` | `sha256:da54eb86849f…` | 2026-11-05 |
| `services/proxy/Dockerfile` | build | `golang:1.26.11-alpine3.24` | `sha256:ae52b5bc6ed0…` | 2026-11-11 |
| `services/proxy/Dockerfile` | final | `alpine:3.24.2` | `sha256:f59abe656b69…` | 2026-11-20 |
| `services/relay/Dockerfile` | build | `golang:1.26.11-alpine3.24` | `sha256:ae52b5bc6ed0…` | 2026-11-17 |
| `services/relay/Dockerfile` | final | `alpine:3.24.2` | `sha256:294b683cb724…` | 2026-11-17 |
| `services/worker/Dockerfile` | uv | `ghcr.io/astral-sh/uv:0.7.20` | `sha256:2fd1b38e3398…` | 2026-08-31 |
| `services/worker/Dockerfile` | deps | `python:3.12-slim-bookworm` | `sha256:da54eb86849f…` | 2026-11-05 |
| `services/worker/Dockerfile` | runtime | `python:3.12-slim-bookworm` | `sha256:da54eb86849f…` | 2026-11-05 |

Two divergences are visible in the table and are not resolved here, because each one changes a published digest and
that is its own change:

- `infra/migrations` runs `alpine:3.24.1`, while `proxy`, `auth` and `relay` run `alpine:3.24.2`.
- `mcp-memory` and `mcp-operator` run `python:3.13-slim-bookworm`, while the other Python services run `3.12`.

## What a build inherits

Each image below is listed with the package manager it actually runs, what it pins, and every index those managers
resolve against at build time. An **index** is mutable: nothing in this repository pins its contents, so two builds of
the same commit can resolve different bytes from it. The base digest pins the packages already inside the image; it
does not pin what a package manager installs on top.

| Dockerfile | OS package manager | Pinned packages | Other resolution at build time | Mutable indexes |
|---|---|---|---|---|
| `infra/compose/v1-single-node/postgres` | `apt-get` (final) | `pgbackrest=2.60.0-1.pgdg12+1` | — | Debian `bookworm`, `bookworm-updates`, `bookworm-security` (`deb.debian.org`) **and** PGDG `bookworm-pgdg` (`apt.postgresql.org`) |
| `infra/migrations` | `apk` (final) | none — package names only | `go mod download` (build; `go.sum`-verified) | Alpine `v3.24` main + community; Go module proxy |
| `services/api` | `apt-get` (runtime) | `libpcre2-8-0=10.42-1+deb12u2` | `uv sync --frozen` from `uv.lock` (deps) | Debian; PyPI (lockfile-pinned) |
| `services/auth` | `apk` (final) | none — package names only | `go mod download` (build; `go.sum`-verified) | Alpine `v3.24` main + community; Go module proxy |
| `services/console` | **none** | — | `corepack prepare pnpm@9.15.9`; `pnpm install --frozen-lockfile` from `pnpm-lock.yaml` | npm registry (pnpm tarball, dependency tarballs) |
| `services/context` | `apt-get` (runtime) | `libpcre2-8-0=10.42-1+deb12u2` | `uv sync --frozen` (stubs, deps) | Debian; PyPI (lockfile-pinned) |
| `services/embedder` | `apt-get` (runtime) | `libpcre2-8-0=10.42-1+deb12u2` | `uv sync --frozen` from `uv.lock` (deps) | Debian; PyPI (lockfile-pinned) |
| `services/mcp-memory` | `apt-get` (runtime) | `libpcre2-8-0=10.42-1+deb12u2` | `uv sync --frozen` from `uv.lock` (deps) | Debian; PyPI (lockfile-pinned) |
| `services/mcp-operator` | `apt-get` (runtime) | `libpcre2-8-0=10.42-1+deb12u2` | `uv sync --frozen` from `uv.lock` (deps) | Debian; PyPI (lockfile-pinned) |
| `services/memory` | `apt-get` (runtime) | `libpcre2-8-0=10.42-1+deb12u2` | `uv sync --frozen` from `uv.lock` (deps) | Debian; PyPI (lockfile-pinned) |
| `services/proxy` | `apk` (final) | none — package names only | `go mod download` (build; `go.sum`-verified) | Alpine `v3.24` main + community; Go module proxy |
| `services/relay` | `apk` (final) | none — package names only | `go mod download` (build; `go.sum`-verified) | Alpine `v3.24` main + community; Go module proxy |
| `services/worker` | `apt-get` (runtime) | `libpcre2-8-0=10.42-1+deb12u2` | `uv sync --frozen` from `uv.lock` (deps) | Debian; PyPI (lockfile-pinned) |

Twelve of the thirteen Dockerfiles run an OS package manager. `services/console` runs none: its stages enable
`corepack`, install `pnpm@9.15.9`, run a frozen install from `pnpm-lock.yaml`, and delete npm, npx and corepack from the
runtime stage. Its drift surface is the npm registry, not an apt or apk index.

**Debian — eight images: `postgres` plus the seven `apt-get` services.** None of them upgrades packages during the
build. Seven run `apt-get update` only to resolve one exact pin, `libpcre2-8-0=10.42-1+deb12u2`. Security fixes in those
images therefore come from the base digest, and the way to take more is to refresh the digest — not to add an upgrade
step, which resolves against a mutable package index and makes the same commit rebuild differently.

An exact version pin still resolves only while the index still publishes that version, and that dependency the upgrade
removal does **not** remove. Bookworm carries `10.42-1+deb12u2` today (verified 2026-11-17), so the pin resolves and the
base already satisfies it. When a security revision supersedes it, the pin has to move in the same change as the base
refresh, or `apt-get install` fails with "Version … was not found" instead of silently drifting.

`infra/compose/v1-single-node/postgres` is the eighth Debian image and the only one that resolves against a **second**
index. It pins `pgbackrest=2.60.0-1.pgdg12+1`, a PGDG build that does not exist in Debian. The upstream `postgres`
image writes `/etc/apt/sources.list.d/pgdg.list`
(`deb … http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main 16`), so this image's `apt-get update` reads
Debian's `debian.sources` and the PGDG index together; the Dockerfile adds no source of its own. Both are visible in the
upstream `pgvector/pgvector:0.8.6-pg16` image this Dockerfile starts from. `bookworm-pgdg` carries both
`2.60.1-1.pgdg12+1` and `2.60.0-1.pgdg12+1` today (verified 2026-11-17), so the pin resolves but is one revision behind
the newest PGDG build: a base refresh moves the base image, not pgBackRest.

**Alpine — four images: `migrations`, `proxy`, `auth`, `relay`.** These do run `apk upgrade --no-cache`, but with
**unpinned package names** (`libcrypto3 libssl3 zlib musl musl-utils` in `proxy`, `auth` and `relay`; `libcrypto3
libssl3` in `migrations`), so each build takes whatever
`dl-cdn.alpinelinux.org/alpine/v3.24/{main,community}` carries at that moment. There the upgrade is real work rather
than a no-op: with the pinned `alpine:3.24.2` base, `libcrypto3`/`libssl3` are installed at `3.5.8-r0`, `musl` at
`1.2.6-r2` and `zlib` at `1.3.2-r0`, while the `v3.24` index carries `3.5.9-r0`, `1.2.6-r3` and `1.4-r0`. Removing those
lines would leave the CRITICAL/HIGH Trivy gate to fail. `infra/migrations` pins the older `alpine:3.24.1`, which
installs `libcrypto3`/`libssl3` at `3.5.7-r0`.

## Refresh procedure

1. **Resolve the registry index digest — never `RepoDigests[0]`.** `podman image inspect --format
   '{{index .RepoDigests 0}}' <image>:<tag>` can return a *platform* manifest digest. On this machine Podman 5.7 lists
   the `linux/amd64` manifest of `alpine:3.24` at `RepoDigests[0]` and the index at `RepoDigests[1]`, so following that
   instruction would replace a multi-architecture pin with an amd64-only one, silently and greenly. Ask the registry
   instead, and refuse anything that is not an index:

   ```bash
   # shellcheck shell=bash
   ref='docker.io/library/alpine:3.24.2'

   digest=$(docker buildx imagetools inspect "$ref" --format '{{.Manifest.Digest}}')
   media_type=$(docker buildx imagetools inspect "$ref" --format '{{.Manifest.MediaType}}')

   case "$media_type" in
     application/vnd.oci.image.index.v1+json | application/vnd.docker.distribution.manifest.list.v2+json) ;;
     *)
       printf 'refusing %s: %s is not a multi-architecture index\n' "$ref" "$media_type" >&2
       exit 1
       ;;
   esac

   printf '%s@%s  (%s)\n' "$ref" "$digest" "$media_type"
   ```

   Only two media types are acceptable for a pin: `application/vnd.oci.image.index.v1+json` (an OCI image index) and
   `application/vnd.docker.distribution.manifest.list.v2+json` (a Docker manifest list).
   `application/vnd.oci.image.manifest.v1+json` and `application/vnd.docker.distribution.manifest.v2+json` are a single
   platform's manifest; do not pin them.

   Confirm the index before editing any Dockerfile — an index prints a `Manifests:` block with one `Name:` per platform,
   a platform manifest prints no such block:

   ```bash
   docker buildx imagetools inspect "docker.io/library/alpine@${digest}"
   ```

   Worked example, run 2026-11-17: the snippet returns
   `sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6` with
   `application/vnd.oci.image.index.v1+json` for `docker.io/library/alpine:3.24.2` — the digest `auth`, `proxy` and
   `relay` already pin — and inspecting that digest lists 16 platform manifests. The same local storage's `alpine:3.24`
   shows the trap: `RepoDigests[0]` is `sha256:0f49f331…`, whose media type is
   `application/vnd.oci.image.manifest.v1+json` (one platform, `linux/amd64`), while the index `sha256:f59abe65…` sits
   at `RepoDigests[1]`. Take the readable tag from the index's `org.opencontainers.image.version` annotation, which
   `docker buildx imagetools inspect <repo>@<digest>` prints with the platform list.
2. Replace the digest in **every** file that uses it — a partial refresh is how the `alpine` divergence above happened.
3. Build the affected images and run the blocking scan. The selection is the one `docker-publish.yml` enforces on every
   blocking pass — `--severity CRITICAL,HIGH --ignore-unfixed --exit-code 1` — with the locally built tag in place of
   the workflow's `--input /tmp/<service>.tar` OCI archive. Where a job writes SARIF it does so in a second pass with
   `--exit-code 0`, so the report still uploads and the job still fails on the blocking pass. Without `--exit-code 1`
   Trivy prints findings and exits 0, so this step cannot fail:

   ```bash
   docker build -t ibex-api:local -f services/api/Dockerfile .
   trivy image --severity CRITICAL,HIGH --ignore-unfixed --exit-code 1 ibex-api:local
   ```

   `--ignore-unfixed` stays on both sides: a finding with no fixed version is not something this step can act on.
4. Update the tables here in the same change, including the pin date, and the package-inventory row if a pin moved.
5. If the refresh changes a CVE disposition, update the exemption record it belongs to.

## Regenerating

```bash
# Every FROM, with the stage alias (33 lines today)
grep -rn '^\s*FROM ' --include='Dockerfile*' .

# The package-manager table: one line per Dockerfile. A file with no package manager
# in the second column runs none (today: services/console); every other column is read
# from the Dockerfile by hand from this output plus the pins below.
find . -name 'Dockerfile*' -not -path './node_modules/*' -print0 |
  sort -z |
  while IFS= read -r -d '' f; do
    printf '%-52s ' "$f"
    grep -o -E 'apt-get (update|install|upgrade)|apk (add|upgrade)|corepack prepare|pnpm install|go mod download|uv (sync|pip install)' "$f" |
      sort -u | tr '\n' ' '
    printf '\n'
  done

# The pinned versions, and which instruction carries them
grep -rn -E -A2 'apt-get install|apk upgrade' --include='Dockerfile*' .

# The registry index digest and its media type (see Refresh procedure)
docker buildx imagetools inspect <ref> --format '{{.Manifest.Digest}} {{.Manifest.MediaType}}'

# What a digest actually is: an index prints a Manifests: block, a platform manifest does not
docker buildx imagetools inspect <repo>@sha256:<digest>

# When it entered a given file
git log -1 --format=%ad --date=short origin/main -S'sha256:<digest>' -- <path>
```

## Reproducibility status

Recording these pins and removing the in-build upgrade are **necessary but not sufficient** for the row's acceptance
test ("two builds of the same commit produce the same digest"). It remains **unmet**: two builds of the same commit
still differ, because the image config carries a `created` timestamp and each layer records file mtimes from the build
clock. The pins make the *inputs* reviewable; they do not make the *output* stable.

Making the output stable requires a build-time decision that has not been taken — normalising timestamps at the builder
(`--rewrite-timestamp`, `SOURCE_DATE_EPOCH`) and pinning the builder itself. That is deliberately not done here: it
changes how every image is built, and it belongs to its own change with its own verification.
