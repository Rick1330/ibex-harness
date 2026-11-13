"""The command line both MCP services run: ``--check`` (default), ``--update``, or ``--check-base``.

Exit codes: 0 the record matches the surface, 1 the record drifted (every failure
is printed, one per line, to stderr), 2 the ``--path`` value was refused and
nothing was read or written.

``--update`` is the only writer and replaces the record atomically, so an
interrupted run cannot truncate it. ``--path`` must stay inside ``--allow-root``
(the working directory unless set, or ``IBEX_MCP_DESCRIPTOR_ALLOW_ROOT``).

``--check-base <ref>`` runs ``--check`` and then compares the committed record
with the same file at ``<ref>`` (read with ``git show``). A tool that was removed
or whose version, description, or schemas changed needs a live deprecation entry;
an additive change passes. ``--deprecations`` points the comparison at a
deprecation record other than
``engineering/architecture-v2/contracts/deprecations.json`` beside the
repository root.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from mcp_tool_descriptors.base import check_base
from mcp_tool_descriptors.checks import check, update
from mcp_tool_descriptors.paths import ALLOW_ROOT_ENV, RefusedPath
from mcp_tool_descriptors.record import Surface

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_REFUSED = 2


def main(surface: Surface, default_path: Path, argv: Sequence[str] | None = None) -> int:
    """Run one mode for ``surface``; return the process exit code."""
    args = parse_args(surface, default_path, argv)
    try:
        return _run(surface, args)
    except RefusedPath as refusal:
        print(refusal, file=sys.stderr)
        return EXIT_REFUSED


def parse_args(
    surface: Surface, default_path: Path, argv: Sequence[str] | None = None
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"Record or check the {surface.service} MCP tool descriptors.",
        epilog=(
            "--check is the default and never writes. --update replaces the record "
            "atomically and is the only writer. --check-base runs --check and then "
            "compares the record with a git ref. --path must stay inside --allow-root."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="check the committed record (the default)"
    )
    mode.add_argument("--update", action="store_true", help="rewrite the record from the surface")
    mode.add_argument(
        "--check-base",
        metavar="REF",
        default=None,
        help=(
            "run --check, then compare the committed record with the same file at REF "
            "(git show REF:<path>); a removed tool or a changed version, description, or "
            "schema needs a deprecation entry"
        ),
    )
    parser.add_argument("--path", type=Path, default=default_path)
    parser.add_argument(
        "--allow-root",
        type=Path,
        default=None,
        help=(
            "directory --path must stay inside (default: the working directory, or "
            f"{ALLOW_ROOT_ENV} when set)"
        ),
    )
    parser.add_argument(
        "--deprecations",
        type=Path,
        default=None,
        help=(
            "deprecation record --check-base reads (default: "
            "engineering/architecture-v2/contracts/deprecations.json beside the repository root)"
        ),
    )
    args = parser.parse_args(argv)
    if args.deprecations is not None and not args.check_base:
        parser.error("--deprecations requires --check-base")
    return args


def _run(surface: Surface, args: argparse.Namespace) -> int:
    """Run one mode; a refused path has already left through ``main``."""
    if args.update:
        written = update(surface, args.path, args.allow_root)
        print(f"recorded {written} tool(s) in {args.path}")
        return EXIT_OK
    if args.check_base:
        return _run_check_base(surface, args)
    failures = check(surface, args.path, args.allow_root)
    return _report(
        failures,
        args.path,
        f"mcp tool descriptors match the published surface: {args.path}",
    )


def _run_check_base(surface: Surface, args: argparse.Namespace) -> int:
    failures = check(surface, args.path, args.allow_root)
    failures.extend(
        check_base(surface, args.path, args.check_base, args.allow_root, args.deprecations)
    )
    message = f"mcp tool descriptors match the published surface and {args.check_base}: {args.path}"
    return _report(failures, args.path, message)


def _report(failures: list[str], path: Path, success: str) -> int:
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        print(f"mcp tool descriptor check failed: {len(failures)} problem(s) in {path}")
        return EXIT_DRIFT
    print(success)
    return EXIT_OK
