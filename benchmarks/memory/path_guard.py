"""Safe workspace-relative path resolution for HNSW bench CLI outputs."""

from __future__ import annotations

from pathlib import Path


class UnsafePathError(ValueError):
    """Raised when a CLI path escapes the allowed workspace."""


def resolve_workspace_path(
    raw: Path | str,
    *,
    workspace: Path | None = None,
    must_exist: bool = False,
    allow_create_parent: bool = False,
) -> Path:
    """Resolve ``raw`` under ``workspace`` (default: cwd). Rejects escapes.

    Relative paths may not contain ``..``. Absolute paths are allowed only when
    the resolved path stays inside ``workspace`` (so CI/shell scripts can pass
    absolute paths under the repo root).
    """
    text = str(raw)
    if not text or text != text.strip():
        raise UnsafePathError("path must not be empty or whitespace")
    candidate = Path(text)
    root = (workspace or Path.cwd()).resolve()

    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        if ".." in candidate.parts:
            raise UnsafePathError("path must not contain parent references")
        resolved = (root / candidate).resolve()

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError("path escapes workspace") from exc

    if must_exist and not resolved.is_file():
        raise UnsafePathError(f"file not found: {candidate}")
    if allow_create_parent:
        parent = resolved.parent
        try:
            parent.relative_to(root)
        except ValueError as exc:
            raise UnsafePathError("parent path escapes workspace") from exc
    return resolved
