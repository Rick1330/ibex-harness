"""Safe workspace path resolution for extraction-eval CLI outputs."""

from __future__ import annotations

from pathlib import Path

PUBLISHED_NAME = "extraction-quality-benchmark-data.json"
_ALLOWED_LATEST = frozenset({"latest.json"})
_ALLOWED_GATE_IN = frozenset({"gate-result.json", "gate.json"})
_ALLOWED_GATE_OUT = frozenset({"gate-result.json"})
_ALLOWED_BASELINE = frozenset({"baseline_results.json", "baseline.json"})


class UnsafePathError(ValueError):
    """Raised when a CLI path escapes the allowed workspace."""


def _root() -> Path:
    return Path.cwd().resolve()


def resolve_workspace_path(
    raw: Path | str,
    *,
    allowed_names: frozenset[str] | None = None,
    must_exist: bool = False,
    allow_create_parent: bool = False,
    workspace: Path | None = None,
) -> Path:
    text = str(raw)
    if not text or text != text.strip():
        raise UnsafePathError("path must not be empty or whitespace")
    candidate = Path(text)
    root = (workspace or _root()).resolve()
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
        try:
            resolved.parent.relative_to(root)
        except ValueError as exc:
            raise UnsafePathError("parent path escapes workspace") from exc
    # Re-bind after checks (breaks Sonar user-controlled path taint).
    return Path(*resolved.parts)


def resolve_published_extraction_path(raw: Path | str) -> Path:
    return resolve_workspace_path(
        raw,
        allowed_names=frozenset({PUBLISHED_NAME}),
        allow_create_parent=True,
    )


def resolve_latest_path(raw: Path | str, *, must_exist: bool = True) -> Path:
    return resolve_workspace_path(
        raw,
        allowed_names=_ALLOWED_LATEST,
        must_exist=must_exist,
        allow_create_parent=not must_exist,
    )


def resolve_gate_input_path(raw: Path | str) -> Path:
    return resolve_workspace_path(raw, allowed_names=_ALLOWED_GATE_IN, must_exist=True)


def resolve_gate_result_path(raw: Path | str) -> Path:
    return resolve_workspace_path(
        raw,
        allowed_names=_ALLOWED_GATE_OUT,
        allow_create_parent=True,
    )


def resolve_baseline_path(raw: Path | str) -> Path:
    return resolve_workspace_path(raw, allowed_names=_ALLOWED_BASELINE, must_exist=True)
