#!/usr/bin/env python3
"""Fail when the lock resolves a package below the fix that justifies its OSV waiver.

osv-scanner's ``IgnoredVulns`` is advisory-scoped only: an entry suppresses every
version OSV matches for that advisory, not just the version the waiver was
written for. The Nuxt waivers in ``osv-scanner.toml`` exist because the lock
resolves 4.6.4, which is each advisory's own 4.x fix, while OSV still matches a
second, open-ended 3.x range that has no ``fixed`` event. The suppression is
honest only while the installed version is past that fix. On a 3.x resolution
the same entry would hide unpatched code until its expiry date, and nothing
would say so.

This guard is the mechanical half of that reasoning: every package a waiver
relies on must resolve *at or above* the fixed version the waiver cites. It
reads ``pnpm-lock.yaml`` without a YAML parser and takes versions only from the
record keys in the ``packages:`` and ``snapshots:`` sections, so a dependency
*range* (``nuxt: ^4.6.4``) can never be mistaken for a resolution. A package
that is absent from the lock has nothing to waive and passes with a note.

The floors are not in the TOML because OSV's schema has no version constraint;
they live here, next to the advisories they protect.

Exit 1 on a violation, 2 when the lockfile cannot be read or parsed, 0 otherwise.
Stdlib only.

Usage:
    python3 infra/scripts/check-osv-waiver-floor.py
    python3 infra/scripts/check-osv-waiver-floor.py --lockfile /tmp/pnpm-lock.yaml
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from dataclasses import dataclass

LOCKFILE = "pnpm-lock.yaml"

# The record-key layout this parser understands. A different major is a format
# this guard has not been taught, so it refuses instead of reading nothing and
# reporting a pass.
LOCKFILE_MAJOR = "9"

LOCKFILE_VERSION_RE = re.compile(r"^lockfileVersion:\s*'?(\d+)", re.MULTILINE)

# Only these two sections hold resolved records. `importers:` holds requested
# ranges, so it is deliberately not parsed.
RECORD_SECTIONS = ("packages:", "snapshots:")

# A resolved version, optionally with a prerelease or build suffix. A peer
# suffix such as `4.6.4(tnwh27lbj7gh4dedmnyo7k537e)` is stripped before this
# pattern is applied; anything that still does not look like a version (a git
# URL, a `link:` target) is not a release this guard can reason about.
VERSION_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?"
    r"(?:\+[0-9A-Za-z.-]+)?$"
)


@dataclass(frozen=True)
class Waiver:
    """One package a waiver relies on, the fix it cites, and the entries at stake."""

    package: str
    floor: str
    advisories: tuple[str, ...]


# Each floor is the `fixed` version the matching osv-scanner.toml `IgnoredVulns`
# entry names for the 4.x range, and the advisories are the entries that would
# otherwise suppress the advisory for a 3.x match. The two packages are checked
# independently: a waiver can name both, but one passing must not mask the other.
WAIVERS = (
    Waiver(
        package="nuxt",
        floor="4.6.4",
        advisories=(
            "GHSA-f3x9-2chm-73c8",
            "GHSA-96x6-fvhx-49hg",
            "GHSA-hf59-9xwc-2g4p",
            "GHSA-vjh5-4x84-xrqp",
        ),
    ),
    Waiver(
        package="@nuxt/nitro-server",
        floor="4.6.4",
        advisories=(
            "GHSA-f3x9-2chm-73c8",
            "GHSA-hf59-9xwc-2g4p",
            "GHSA-vjh5-4x84-xrqp",
        ),
    ),
)


def version_key(version: str) -> tuple[int, int, int, bool]:
    """Order a version, sorting a prerelease below its release.

    A tuple keeps the comparison stdlib-only. Prerelease labels are not ordered
    against each other (``rc.1`` vs ``rc.2``); they only need to sort below the
    release with the same numbers, which is what ``4.6.4-rc.1`` must do to fail
    the 4.6.4 floor.
    """
    match = VERSION_RE.match(version)
    if match is None:
        raise ValueError(f"not a version: {version!r}")
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        match.group("prerelease") is None,
    )


def _is_record_indent(line: str) -> bool:
    """True when the line sits at the indentation pnpm gives a record key.

    pnpm writes a record key at exactly two spaces and a dependency entry deeper
    than that. The distinction is the whole point: at six spaces,
    `nuxt: ^4.6.4` is a range the importer asked for, and reading it as a
    resolution would compare a range against a floor and pass anything.
    """
    if not line.startswith("  "):
        return False
    return not line.startswith("   ")


def _declares_record_key(stripped: str) -> bool:
    """True when a stripped line is a `key:` record rather than a dependency entry.

    A record key terminates with `:` and always names a package, so it carries an
    `@`; the importer's dependency entry (`nuxt: 4.6.4`) carries none.
    """
    if not stripped.endswith(":"):
        return False
    return "@" in stripped


def _is_quoted(key: str) -> bool:
    """True when pnpm wrapped the key in a matching pair of quotes."""
    if len(key) <= 1:
        return False
    if key[0] not in "'\"":
        return False
    return key[-1] == key[0]


def _record_key(line: str) -> str | None:
    """Return the record key a line declares, or None when it declares none."""
    if not _is_record_indent(line):
        return None
    stripped = line.strip()
    if not _declares_record_key(stripped):
        return None
    key = stripped[:-1].strip()
    if _is_quoted(key):
        return key[1:-1]
    return key


def _is_versioned_package(name: str, version: str) -> bool:
    """True when a split key yielded a package name and a released version."""
    if not name:
        return False
    if not version:
        return False
    return VERSION_RE.match(version) is not None


def _split_resolution(key: str) -> tuple[str, str] | None:
    """Split `@scope/name@1.2.3(peer@4.5.6)` into the package and its version.

    The peer suffix is cut at the first `(` *before* the name is split from the
    version, because a peer suffix carries `@` of its own:
    `nuxt@4.6.4(@babel/core@7.29.7)` would otherwise split at the peer's `@`
    and read `7.29.7)` as the version. Cutting first leaves `nuxt@4.6.4`, where
    the last `@` is the one before the version. Returns None for a key that
    carries no usable version.
    """
    head = key.split("(", 1)[0].strip()
    name, _, version = head.rpartition("@")
    if not _is_versioned_package(name, version):
        return None
    return name, version


def lock_resolutions(text: str) -> dict[str, set[str]]:
    """Map each package name to every version the lock resolves it to."""
    resolutions: dict[str, set[str]] = {}
    section = ""
    for line in text.splitlines():
        if line and not line.startswith((" ", "\t")):
            section = line.strip()
            continue
        if section not in RECORD_SECTIONS:
            continue
        key = _record_key(line)
        if key is None:
            continue
        resolution = _split_resolution(key)
        if resolution is None:
            continue
        name, version = resolution
        resolutions.setdefault(name, set()).add(version)
    return resolutions


def lockfile_major(text: str) -> str | None:
    """Return the lockfile format major, or None when the header is absent."""
    match = LOCKFILE_VERSION_RE.search(text)
    return match.group(1) if match else None


def check(resolutions: dict[str, set[str]]) -> tuple[list[str], list[str]]:
    """Return (notes, problems) with every waiver checked on its own."""
    notes: list[str] = []
    problems: list[str] = []
    for waiver in WAIVERS:
        versions = resolutions.get(waiver.package)
        if not versions:
            notes.append(
                f"{waiver.package}: absent from the lock, so there is nothing "
                "for its waiver to cover"
            )
            continue
        floor_key = version_key(waiver.floor)
        below = sorted(
            (version for version in versions if version_key(version) < floor_key),
            key=version_key,
        )
        if below:
            advisories = ", ".join(waiver.advisories)
            problems.append(
                f"{waiver.package} {', '.join(below)} is below the {waiver.floor} "
                f"floor that protects waiver {advisories}"
            )
            continue
        notes.append(
            f"{waiver.package} {', '.join(sorted(versions, key=version_key))}: "
            f"at or above {waiver.floor}"
        )
    return notes, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail when a waived package resolves below its fixed version.",
    )
    parser.add_argument(
        "--lockfile",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parents[2] / LOCKFILE,
        help=f"lockfile to check (default: <repo-root>/{LOCKFILE})",
    )
    args = parser.parse_args(argv)

    try:
        text = args.lockfile.read_text(encoding="utf-8")
    except OSError as error:
        print(f"check-osv-waiver-floor: cannot read {args.lockfile}: {error}", file=sys.stderr)
        return 2

    major = lockfile_major(text)
    if major != LOCKFILE_MAJOR:
        print(
            f"check-osv-waiver-floor: unsupported lockfileVersion "
            f"{major or '<missing>'} in {args.lockfile}; this parser is written "
            f"for {LOCKFILE_MAJOR}.x. Teach it the new record layout before "
            "trusting a green gate.",
            file=sys.stderr,
        )
        return 2

    resolutions = lock_resolutions(text)
    if not resolutions:
        # Fail closed: zero records means the parser stopped matching the
        # lockfile format, not that the repository stopped resolving anything.
        print(
            "check-osv-waiver-floor: no package resolutions found in "
            f"{args.lockfile}; the parser no longer matches the lockfile format",
            file=sys.stderr,
        )
        return 2

    notes, problems = check(resolutions)
    if problems:
        print(
            "check-osv-waiver-floor: a waived package resolves below the fixed "
            "version its waiver cites:",
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            "\nIgnoredVulns is advisory-scoped, so it suppresses the advisory "
            "for the open-ended 3.x range as well. Upgrade the package to the "
            "floor, or remove that waiver from osv-scanner.toml and let "
            "osv-scan fail on the version actually resolved.",
            file=sys.stderr,
        )
        return 1

    for note in notes:
        print(f"check-osv-waiver-floor: {note}")
    print("check-osv-waiver-floor: every waived package resolves at or above its fixed version")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
