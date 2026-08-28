"""Write-path error helpers."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

_ACTIVE_HASH_INDEX = "idx_memories_org_agent_content_hash_active"


def _integrity_haystack(orig: object, exc: IntegrityError) -> str:
    parts: list[str] = []
    parts.append(str(getattr(orig, "constraint_name", "") or ""))
    diag = getattr(orig, "diag", None)
    if diag is not None:
        parts.append(str(getattr(diag, "constraint_name", "") or ""))
    parts.append(str(getattr(orig, "detail", "") or ""))
    parts.append(str(orig))
    parts.append(str(exc))
    return " ".join(parts)


def is_active_content_hash_violation(exc: IntegrityError) -> bool:
    """True when Postgres rejected an active (org, agent, content_hash) duplicate."""
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate != "23505":
        return False
    haystack = _integrity_haystack(orig, exc)
    if _ACTIVE_HASH_INDEX in haystack:
        return True
    lowered = haystack.lower()
    return "content_hash" in lowered and (
        "already exists" in lowered or "duplicate key" in lowered
    )
