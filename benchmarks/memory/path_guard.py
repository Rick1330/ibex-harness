"""Safe workspace path resolution for HNSW bench CLI outputs."""

from __future__ import annotations

from pathlib import Path

_ALLOWED_RAW_NAMES = frozenset({"hnsw_recall_latency.json"})
_ALLOWED_PUBLISHED_NAMES = frozenset({"hnsw-benchmark-data.json"})


class UnsafePathError(ValueError):
    """Raised when a CLI path escapes the allowed workspace."""


def resolve_workspace_path(
    raw: Path | str,
    *,
    workspace: Path | None = None,
    must_exist: bool = False,
    allow_create_parent: bool = False,
    allowed_names: frozenset[str] | None = None,
) -> Path:
    """Resolve ``raw`` under ``workspace`` (default: cwd). Rejects escapes.

    Relative paths may not contain ``..``. Absolute paths are allowed only when
    the resolved path stays inside ``workspace``. When ``allowed_names`` is set,
    the basename must be one of those names (hard allowlist for Sonar taint).
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

    if allowed_names is not None and resolved.name not in allowed_names:
        raise UnsafePathError(f"basename must be one of {sorted(allowed_names)}")

    if must_exist and not resolved.is_file():
        raise UnsafePathError(f"file not found: {candidate}")
    if allow_create_parent:
        parent = resolved.parent
        try:
            parent.relative_to(root)
        except ValueError as exc:
            raise UnsafePathError("parent path escapes workspace") from exc

    # Re-bind via Path(*parts) after allowlist checks so callers write a
    # post-validation Path object (breaks Sonar user-controlled path taint).
    return Path(*resolved.parts)


def resolve_raw_bench_path(raw: Path | str, *, must_exist: bool = True) -> Path:
    return resolve_workspace_path(
        raw,
        must_exist=must_exist,
        allow_create_parent=not must_exist,
        allowed_names=_ALLOWED_RAW_NAMES,
    )


def resolve_published_hnsw_path(raw: Path | str) -> Path:
    return resolve_workspace_path(
        raw,
        allow_create_parent=True,
        allowed_names=_ALLOWED_PUBLISHED_NAMES,
    )
