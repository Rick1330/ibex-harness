#!/usr/bin/env bash
# Assert that every versioned release image exists in the registry.
#
# The reusable docker-publish workflow can finish green while every publish job
# is skipped, so its job status is not evidence that an image was published.
# This inspects the published artifact at the release tag instead, and fails
# naming every service that is absent.
#
# Usage:
#   verify-release-images.sh --tag vX.Y.Z --services auth,proxy,api \
#     [--registry ghcr.io]
#
# Environment:
#   GITHUB_REPOSITORY  owner/name of the repository (required)
#
# Exits 0 only when every service resolves to a sha256 digest at the tag.
set -euo pipefail

usage() {
  cat <<'USAGE'
usage: verify-release-images.sh --tag <vX.Y.Z> --services <svc[,svc...]> [--registry <host>]
USAGE
}

tag=""
services_csv=""
registry="ghcr.io"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag=*) tag="${1#*=}" ;;
    --services=*) services_csv="${1#*=}" ;;
    --registry=*) registry="${1#*=}" ;;
    --tag|--services|--registry)
      opt="$1"
      shift
      if [[ $# -eq 0 ]]; then
        usage >&2
        exit 2
      fi
      case "$opt" in
        --tag) tag="$1" ;;
        --services) services_csv="$1" ;;
        --registry) registry="$1" ;;
      esac
      ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done

if [[ ! "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  printf '::error::verify-release-images: unsupported release tag: %s\n' "$tag" >&2
  exit 2
fi
if [[ -z "$services_csv" ]]; then
  printf '::error::verify-release-images: --services is required\n' >&2
  exit 2
fi
if [[ -z "${GITHUB_REPOSITORY:-}" ]]; then
  printf '::error::verify-release-images: GITHUB_REPOSITORY is not set\n' >&2
  exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
  printf '::error::verify-release-images: docker is not available\n' >&2
  exit 2
fi

repository_lc="${GITHUB_REPOSITORY,,}"
IFS=',' read -r -a services <<<"$services_csv"
missing=()

for service in "${services[@]}"; do
  if [[ ! "$service" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    printf '::error::verify-release-images: invalid service name: %s\n' "$service" >&2
    exit 2
  fi
  reference="${registry}/${repository_lc}/${service}:${tag}"
  digest=""
  if digest="$(docker buildx imagetools inspect "$reference" \
    --format '{{json .Manifest.Digest}}')"; then
    digest="${digest//\"/}"
    if [[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
      printf 'ok      %s %s\n' "$reference" "$digest"
      continue
    fi
  fi
  printf '::error::missing release image: %s\n' "$reference"
  missing+=("$service")
done

if (( ${#missing[@]} > 0 )); then
  printf '::error::%s published no image for: %s\n' "$tag" "${missing[*]}" >&2
  exit 1
fi

printf 'verified %d release images at %s\n' "${#services[@]}" "$tag"
