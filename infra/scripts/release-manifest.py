#!/usr/bin/env python3
"""Generate release-manifest.json for a version tag.

The manifest ties a platform release to the exact container image digests,
contract hashes, and migration versions published with it. It is generated
after the versioned images are pushed and uploaded to the GitHub Release.

Shelling out is limited to fixed argv lists (docker buildx and git). No shell
is used, and every argument is validated before it reaches the process.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

MANIFEST_VERSION = 1
TAG_RE = re.compile(r"^v([0-9]+)\.([0-9]+)\.([0-9]+)$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
MIGRATION_RE = re.compile(r"^([0-9]+)_")


class ManifestError(RuntimeError):
    """Raised when verified manifest inputs are missing or malformed."""


@dataclass(frozen=True)
class ManifestSpec:
    """Everything the manifest generator needs, resolved once."""

    root: Path
    tag: str
    repository: str
    commit: str
    generated_at: str
    digest_map: dict[str, str] | None = None
    services: list[str] | None = None


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


def _migration_versions(directory: Path) -> list[int]:
    versions: list[int] = []
    for path in directory.glob("*.up.sql"):
        match = MIGRATION_RE.match(path.name)
        if match:
            versions.append(int(match.group(1)))
    return versions


def _migration_max(root: Path, engine: str) -> int:
    directory = root / "infra" / "migrations" / engine
    versions = _migration_versions(directory)
    if not versions:
        msg = f"no {engine} migration versions under {directory}"
        raise ManifestError(msg)
    return max(versions)


def _discovered_services(root: Path) -> list[str]:
    return sorted(path.parent.name for path in (root / "services").glob("*/Dockerfile"))


def _validate_services(root: Path, services: list[str]) -> list[str]:
    for service in services:
        if not (root / "services" / service / "Dockerfile").is_file():
            msg = f"missing Dockerfile for service: {service}"
            raise ManifestError(msg)
    return services


def _services(root: Path, requested: list[str] | None) -> list[str]:
    services = (
        _validate_services(root, requested)
        if requested
        else _validate_services(root, _discovered_services(root))
    )
    if not services:
        msg = "no service Dockerfiles found"
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


def _executable(name: str) -> str:
    path = shutil.which(name)
    if not path:
        msg = f"{name} is required to resolve release inputs"
        raise ManifestError(msg)
    return path


def _inspect_digest(command: list[str], reference: str) -> str:
    try:
        # Fixed argv, no shell. ``reference`` is built from a validated tag,
        # a validated service name, and the repository constant.
        # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit
        result = subprocess.run(  # nosec B603
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        msg = "docker is required to resolve image digests"
        raise ManifestError(msg) from exc
    except subprocess.TimeoutExpired as exc:
        msg = f"timed out resolving {reference}"
        raise ManifestError(msg) from exc
    except subprocess.CalledProcessError as exc:
        msg = f"could not resolve {reference}: {exc.stderr.strip()}"
        raise ManifestError(msg) from exc
    return result.stdout


def _digest_from_registry(reference: str) -> str:
    command = [
        _executable("docker"),
        "buildx",
        "imagetools",
        "inspect",
        reference,
        "--format",
        "{{json .Manifest.Digest}}",
    ]
    digest = _inspect_digest(command, reference).strip().strip('"')
    if not DIGEST_RE.fullmatch(digest):
        msg = f"registry returned an invalid digest for {reference}: {digest}"
        raise ManifestError(msg)
    return digest


def _image_digests(spec: ManifestSpec, services: list[str]) -> dict[str, str]:
    if spec.digest_map is not None:
        return {
            service: _digest_from_map(service, spec.digest_map)
            for service in services
        }
    prefix = f"ghcr.io/{spec.repository.lower()}"
    return {
        service: _digest_from_registry(f"{prefix}/{service}:{spec.tag}")
        for service in services
    }


def _git_head(root: Path) -> str:
    git = shutil.which("git")
    if not git:
        return ""
    try:
        # Fixed argv, absolute executable, no shell.
        # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit
        return subprocess.check_output(  # nosec B603
            [git, "-C", str(root), "rev-parse", "HEAD"],
            text=True,
            timeout=10,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""


def _manifest_document(
    spec: ManifestSpec,
    platform_version: str,
    images: dict[str, str],
) -> dict[str, object]:
    return {
        "manifest_version": MANIFEST_VERSION,
        "tag": spec.tag,
        "platform_version": platform_version,
        "generated_at": spec.generated_at,
        "source": {"repository": spec.repository, "commit": spec.commit},
        "images": images,
        "contracts": {
            "openapi_sha256": _file_sha256(
                spec.root / "services" / "api" / "openapi.snapshot.json"
            ),
            "proto_sha256": _proto_sha256(spec.root),
        },
        "migrations": {
            "postgres": _migration_max(spec.root, "postgres"),
            "clickhouse": _migration_max(spec.root, "clickhouse"),
        },
        "bundles": [],
    }


def _valid_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _validate_metadata(spec: ManifestSpec) -> None:
    if not REPOSITORY_RE.fullmatch(spec.repository):
        msg = f"invalid repository: {spec.repository}"
        raise ManifestError(msg)
    if not COMMIT_RE.fullmatch(spec.commit):
        msg = f"invalid commit: {spec.commit}"
        raise ManifestError(msg)
    if not _valid_timestamp(spec.generated_at):
        msg = f"invalid generated_at: {spec.generated_at}"
        raise ManifestError(msg)


def build_manifest(spec: ManifestSpec) -> dict[str, object]:
    match = TAG_RE.fullmatch(spec.tag)
    if not match:
        msg = f"invalid release tag: {spec.tag}"
        raise ManifestError(msg)
    _validate_metadata(spec)
    platform_version = ".".join(match.groups())
    services = _services(spec.root, spec.services)
    return _manifest_document(spec, platform_version, _image_digests(spec, services))


def _is_digest_map(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    )


def _contained_path(raw: str, root: Path, label: str) -> Path:
    """Resolve a CLI path and refuse anything outside the release checkout."""
    candidate = Path(raw)
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        msg = f"{label} must resolve inside {root}"
        raise ManifestError(msg)
    return resolved


def _digest_map(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not _is_digest_map(data):
        msg = "--digest-map must contain a JSON object of service to digest"
        raise ManifestError(msg)
    return cast("dict[str, str]", data)


def _split_services(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [service.strip() for service in value.split(",") if service.strip()]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", default="release-manifest.json")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY", "Rick1330/ibex-harness"),
    )
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    commit = args.commit or _git_head(root)
    if not commit:
        parser.error("--commit or GITHUB_SHA is required")
    generated_at = args.generated_at or datetime.now(UTC).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    try:
        digest_map_path = (
            _contained_path(args.digest_map, root, "--digest-map")
            if args.digest_map
            else None
        )
        output = _contained_path(args.output, root, "--output")
        spec = ManifestSpec(
            root=root,
            tag=args.tag,
            repository=args.repository,
            commit=commit,
            generated_at=generated_at,
            digest_map=_digest_map(digest_map_path) if digest_map_path else None,
            services=_split_services(args.services),
        )
        manifest = build_manifest(spec)
        output.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (ManifestError, OSError, ValueError) as exc:
        print(f"release-manifest: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
