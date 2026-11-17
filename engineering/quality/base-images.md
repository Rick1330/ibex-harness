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
| `alpine:3.24.2` | `sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6` | 2026-09-17 | 2026-09-23 |
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
| `services/auth/Dockerfile` | final | `alpine:3.24.2` | `sha256:294b683cb724…` | 2026-09-23 |
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
| `services/proxy/Dockerfile` | final | `alpine:3.24.2` | `sha256:294b683cb724…` | 2026-09-23 |
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

The Debian-based images (`python`, `node`, and the `pgvector` runtime) do **not** upgrade packages during the build.
They run `apt-get update` only to resolve the one pin they carry (`libpcre2-8-0=10.42-1+deb12u2`). Security fixes in
those images therefore come from the base digest, and the way to take more is to refresh the digest — not to add an
upgrade step, which resolves against a mutable package index and makes the same commit rebuild differently.

That keeps one dependency on the index that the upgrade removal does **not** remove: an exact version pin resolves only
while Debian still publishes that version. Bookworm carries `10.42-1+deb12u2` today (verified 2026-11-17), so the pin
resolves and the base already satisfies it. When a security revision supersedes it, the pin has to move in the same
change as the base refresh, or `apt-get install` fails with "Version … was not found" instead of silently drifting.

The Alpine-based images (`proxy`, `auth`, `relay`, `migrations`) do run `apk upgrade --no-cache` for named packages,
and there the upgrade is real work rather than a no-op: with the pinned `alpine:3.24.2` base, `libcrypto3`/`libssl3`
are installed at `3.5.8-r0`, `musl` at `1.2.6-r2` and `zlib` at `1.3.2-r0`, while the `v3.24` index carries `3.5.9-r0`,
`1.2.6-r3` and `1.4-r0`. Removing those lines would leave the CRITICAL/HIGH Trivy gate to fail. `infra/migrations` pins
the older `alpine:3.24.1`, which installs `libcrypto3`/`libssl3` at `3.5.7-r0`.

## Refresh procedure

1. Pick the new digest: `podman pull <image>:<tag>` then `podman image inspect --format '{{index .RepoDigests 0}}' <image>:<tag>`
   for the index digest, and record the annotation with `podman manifest inspect <image>@<digest>`.
2. Replace the digest in **every** file that uses it — a partial refresh is how the `alpine` divergence above happened.
3. Build the affected images and run the blocking scan (`trivy image --severity CRITICAL,HIGH --ignore-unfixed`).
4. Update both tables here in the same change, including the pin date.
5. If the refresh changes a CVE disposition, update the exemption record it belongs to.

## Regenerating

```bash
# Every FROM, with the stage alias (33 lines today)
grep -rn '^\s*FROM ' --include='Dockerfile*' .

# What a digest actually is
podman manifest inspect <repo>@sha256:<digest>

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
