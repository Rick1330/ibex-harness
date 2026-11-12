"""The command line both MCP services run: ``--check`` (default) or ``--update``.

Exit codes: 0 the record matches the surface, 1 the record drifted (every failure
is printed, one per line, to stderr), 2 the ``--path`` value was refused and
nothing was read or written.

``--update`` is the only writer and replaces the record atomically, so an
interrupted run cannot truncate it. ``--path`` must stay inside ``--allow-root``
(the working directory unless set, or ``IBEX_MCP_DESCRIPTOR_ALLOW_ROOT``).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

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
            "atomically and is the only writer. --path must stay inside --allow-root."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="check the committed record (the default)"
    )
    mode.add_argument("--update", action="store_true", help="rewrite the record from the surface")
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
    return parser.parse_args(argv)


def _run(surface: Surface, args: argparse.Namespace) -> int:
    """Run one mode; a refused path has already left through ``main``."""
    if args.update:
        written = update(surface, args.path, args.allow_root)
        print(f"recorded {written} tool(s) in {args.path}")
        return EXIT_OK
    failures = check(surface, args.path, args.allow_root)
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        print(f"mcp tool descriptor check failed: {len(failures)} problem(s) in {args.path}")
        return EXIT_DRIFT
    print(f"mcp tool descriptors match the published surface: {args.path}")
    return EXIT_OK
