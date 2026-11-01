#!/usr/bin/env python3
"""Generate release-manifest.json for a version tag.

The manifest ties a platform release to the exact container image digests,
contract hashes, and migration versions published with it. It is generated
after the versioned images are pushed and uploaded to the GitHub Release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

MANIFEST_VERSION = 1
TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
MIGRATION_RE = re.compile(r"^(\d+)_")


class ManifestError(RuntimeError):
    """Raised when verified manifest inputs are missing or malformed."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        msg = f"missing contract file: {path}"
        raise ManifestError(msg)
    return _sha256(path.read_bytes())


def _proto_sha256(root: Path) -> str:
    proto_root = root / "packages" / "proto"
    files = sorted(proto_root.rglob("*.proto"))
    if not files:
        msg = f"no .proto sources under {proto_root}"
        raise ManifestError(msg)
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(proto_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _migration_max(root: Path, engine: str) -> int:
    directory = root / "infra" / "migrations" / engine
    versions = [
        int(match.group(1))
        for path in directory.glob("*.up.sql")
        if (match := MIGRATION_RE.match(path.name)) is not None
    ]
    if not versions:
        msg = f"no {engine} migration versions under {directory}"
        raise ManifestError(msg)
    return max(versions)


def _services(root: Path, requested: list[str] | None) -> list[str]:
    if requested:
        services = sorted(requested)
    else:
        services = sorted(
            path.parent.name for path in (root / "services").glob("*/Dockerfile")
        )
    if not services:
        msg = "no service Dockerfiles found"
        raise ManifestError(msg)
    for service in services:
        if not (root / "services" / service / "Dockerfile").is_file():
            msg = f"missing Dockerfile for service: {service}"
            raise ManifestError(msg)
    return services


def _digest_from_map(service: str, digest_map: dict[str, str]) -> str:
    digest = digest_map.get(service)
    if not digest:
        msg = f"missing digest for service: {service}"
        raise ManifestError(msg)
    if not DIGEST_RE.fullmatch(digest):
        msg = f"invalid digest for {service}: {digest}"
        raise ManifestError(msg)
    return digest


def _digest_from_registry(reference: str) -> str:
    command = [
        "docker",
        "buildx",
        "imagetools",
        "inspect",
        reference,
        "--format",
        "{{json .Manifest.Digest}}",
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        msg = "docker is required to resolve image digests"
        raise ManifestError(msg) from exc
    except subprocess.CalledProcessError as exc:
        msg = f"could not resolve {reference}: {exc.stderr.strip()}"
        raise ManifestError(msg) from exc
    digest = result.stdout.strip().strip('"')
    if not DIGEST_RE.fullmatch(digest):
        msg = f"registry returned an invalid digest for {reference}: {digest}"
        raise ManifestError(msg)
    return digest


def _git_head(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""


def build_manifest(
    *,
    root: Path,
    tag: str,
    repository: str,
    commit: str,
    generated_at: str,
    digest_map: dict[str, str] | None = None,
    services: list[str] | None = None,
) -> dict[str, object]:
    match = TAG_RE.fullmatch(tag)
    if not match:
        msg = f"invalid release tag: {tag}"
        raise ManifestError(msg)
    platform_version = ".".join(match.groups())
    image_prefix = f"ghcr.io/{repository.lower()}"
    images: dict[str, str] = {}
    for service in _services(root, services):
        if digest_map is not None:
            images[service] = _digest_from_map(service, digest_map)
        else:
            images[service] = _digest_from_registry(f"{image_prefix}/{service}:{tag}")
    return {
        "manifest_version": MANIFEST_VERSION,
        "tag": tag,
        "platform_version": platform_version,
        "generated_at": generated_at,
        "source": {"repository": repository, "commit": commit},
        "images": images,
        "contracts": {
            "openapi_sha256": _file_sha256(
                root / "services" / "api" / "openapi.snapshot.json"
            ),
            "proto_sha256": _proto_sha256(root),
        },
        "migrations": {
            "postgres": _migration_max(root, "postgres"),
            "clickhouse": _migration_max(root, "clickhouse"),
        },
        "bundles": [],
    }


def _digest_map(path: str) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in data.items()
    ):
        msg = "--digest-map must contain a JSON object of service to digest"
        raise ManifestError(msg)
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", default="release-manifest.json")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--repository", default="Rick1330/ibex-harness")
    parser.add_argument("--commit", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--generated-at", default=None)
    parser.add_argument(
        "--digest-map",
        default=None,
        help="JSON file mapping service to digest; skips registry resolution",
    )
    parser.add_argument(
        "--services",
        default=None,
        help="comma-separated service names; defaults to discovered Dockerfiles",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    commit = args.commit or _git_head(root)
    if not commit:
        parser.error("--commit or GITHUB_SHA is required")
    generated_at = args.generated_at or datetime.now(UTC).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    services = (
        [service.strip() for service in args.services.split(",") if service.strip()]
        if args.services
        else None
    )
    try:
        digest_map = _digest_map(args.digest_map) if args.digest_map else None
        manifest = build_manifest(
            root=root,
            tag=args.tag,
            repository=args.repository,
            commit=commit,
            generated_at=generated_at,
            digest_map=digest_map,
            services=services,
        )
    except (ManifestError, OSError, json.JSONDecodeError) as exc:
        print(f"release-manifest: {exc}", file=sys.stderr)
        return 1

    output = Path(args.output)
    output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
