"""Confinement for the caller-supplied record path (``--path``).

``--path`` comes from a command line, so neither mode reads or writes it until it
passes here: a path carrying a ``..`` segment is refused outright (an escape that
is also hard to review), the resolved path must stay inside the allow-root (the
working directory unless ``--allow-root`` or ``IBEX_MCP_DESCRIPTOR_ALLOW_ROOT``
names another tree), and an existing target must be a regular file, so a
directory or a device cannot be read or replaced. The resolved path is returned,
so every later read and write uses the checked value and a symlink cannot
redirect it after the check.

A missing target is not refused: the caller holds the ``missing-descriptor``
message, which names the command that writes the record.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

# Widens the tree a ``--path`` value may resolve under. Unset means the working
# directory; the tests point it at their temporary directory.
ALLOW_ROOT_ENV: Final = "IBEX_MCP_DESCRIPTOR_ALLOW_ROOT"


class RefusedPath(Exception):
    """A ``--path`` value failed confinement; the CLI reports it and exits 2."""


def default_allow_root() -> Path:
    """The tree a ``--path`` value may live under: the working directory by default."""
    raw = os.environ.get(ALLOW_ROOT_ENV, "").strip()
    return Path.cwd() if not raw else Path(raw).resolve()


def confine(path: Path, allow_root: Path | None) -> Path:
    """Prove a caller-supplied record path stays inside the allow-root."""
    root = default_allow_root() if allow_root is None else allow_root.resolve()
    if ".." in path.parts:
        raise RefusedPath(f"refusing {path}: it contains a '..' segment")
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise RefusedPath(
            f"refusing {path}: it resolves outside {root}; pass --allow-root or set "
            f"{ALLOW_ROOT_ENV}"
        )
    if resolved.exists() and not resolved.is_file():
        raise RefusedPath(f"refusing {path}: it is not a regular file")
    return resolved
