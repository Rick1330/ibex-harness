"""Rules every registry row shares, whatever surface it names.

A row must carry exactly its surface's fields, non-empty; draw from the closed
``stability``/``status`` vocabularies; not still read as a scaffold; cite
evidence that resolves to a regular file inside the repository; and appear at
most once. Those rules are identical for ``routes``, ``grpc_methods`` and
``mcp_tools``, so they live here and the surface modules add only what differs.

Standard library only; reads no files except the evidence paths it resolves.
"""

from __future__ import annotations

from pathlib import Path

from contract_registry_model import (
    REQUIRED_FIELDS,
    SCAFFOLD_OWNER,
    STABILITIES,
    STATUSES,
    CheckContext,
    non_empty_str,
    root_label,
)


def row_key(row: object) -> str | None:
    if not isinstance(row, dict):
        return None
    key = row.get("key")
    if not isinstance(key, str):
        return None
    return key


def row_shape_failures(
    row: dict[str, object], label: str, fields: tuple[str, ...] = REQUIRED_FIELDS
) -> list[str]:
    """Field rules: every required field present, no unknown field, none empty."""
    failures: list[str] = []
    missing = [field for field in fields if field not in row]
    unknown = sorted(set(row) - set(fields))
    if missing:
        failures.append(f"missing-field: {label} lacks {', '.join(missing)}")
    if unknown:
        failures.append(f"unknown-field: {label} has {', '.join(unknown)}")
    empty = [field for field in fields if isinstance(row.get(field), str) and not row[field]]
    if empty:
        failures.append(f"empty-field: {label} has empty {', '.join(empty)}")
    return failures


def row_enum_failures(
    row: dict[str, object], key: str, *, check_stability: bool = True
) -> list[str]:
    """The closed vocabularies a row must draw from."""
    failures: list[str] = []
    stability = row.get("stability")
    if check_stability and stability not in STABILITIES:
        failures.append(
            f"unknown-enum: {key} has stability {stability!r}; expected one of {sorted(STABILITIES)}"
        )
    status = row.get("status")
    if status not in STATUSES:
        failures.append(
            f"unknown-enum: {key} has status {status!r}; expected one of {sorted(STATUSES)}"
        )
    return failures


def row_scaffold_failures(row: dict[str, object], key: str) -> list[str]:
    """A scaffold must not read as a claim: no ``unregistered`` status, no sentinel owner."""
    failures: list[str] = []
    if row.get("status") == "unregistered":
        failures.append(
            f"unregistered: {key} is scaffolded but not registered; record owner, stability, and status"
        )
    if row.get("owner") == SCAFFOLD_OWNER:
        failures.append(
            f"unassigned-owner: {key} still holds the {SCAFFOLD_OWNER} scaffold sentinel; set the real "
            "owner, review stability, record status, and point evidence at a file that exists"
        )
    return failures


def evidence_failure(evidence: str, root: Path) -> str | None:
    """Return the rule ``evidence`` breaks, or ``None`` when it is a usable citation.

    Three rules, checked in this order, so the message names the one that failed:

    1. it resolves inside ``root``: a relative path resolves under ``root``, and an
       absolute path outside the tree, a ``../`` escape, or a symlink pointing
       outside the tree is rejected;
    2. it exists;
    3. it is a regular file, not a directory.
    """
    root_resolved = root.resolve()
    resolved = resolve_evidence(evidence, root)
    if resolved is None:
        return "cannot be resolved"
    if not resolved.is_relative_to(root_resolved):
        return (
            f"resolves outside {root_label(root)}; evidence must cite a file inside the repository"
        )
    return evidence_file_failure(resolved, root)


def resolve_evidence(evidence: str, root: Path) -> Path | None:
    candidate = Path(evidence)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        return candidate.resolve()
    except OSError:
        return None


def evidence_file_failure(resolved: Path, root: Path) -> str | None:
    if not resolved.exists():
        return f"does not exist under {root_label(root)}"
    if resolved.is_file():
        return None
    kind = "a directory" if resolved.is_dir() else "not a regular file"
    return f"is not a file (it is {kind})"


def row_evidence_failures(row: dict[str, object], key: str, context: CheckContext) -> list[str]:
    evidence = row.get("evidence")
    if not non_empty_str(evidence):
        return []
    reason = evidence_failure(str(evidence), context.root)
    if reason is None:
        return []
    return [f"missing-evidence: {key} cites {evidence!r}, which {reason}"]


def unsorted_failures(rows: list[object], label: str = "routes") -> list[str]:
    """Report the first row that is out of order, naming what it is and what belongs there."""
    keys = [str(row.get("key", "")) for row in rows if isinstance(row, dict)]
    for index, expected in enumerate(sorted(keys)):
        if keys[index] != expected:
            return [
                (
                    f"unsorted-registry: {label}[{index}] is {keys[index]!r}; "
                    f"expected {expected!r} (rows are sorted by key)"
                )
            ]
    return []


def duplicate_key_failures(rows: list[object], label: str) -> list[str]:
    """One row per key, so a malformed earlier row cannot hide behind a later one."""
    seen: dict[str, int] = {}
    failures: list[str] = []
    for index, row in enumerate(rows):
        key = row_key(row)
        if key is None:
            continue
        if key in seen:
            failures.append(
                f"duplicate-key: {key} appears at {label}[{seen[key]}] and {label}[{index}]"
            )
        else:
            seen[key] = index
    return failures


def contract_claim(row: object) -> tuple[str, str] | None:
    if not isinstance(row, dict):
        return None
    contract_id = row.get("contract_id")
    if not non_empty_str(contract_id):
        return None
    return str(contract_id), str(row.get("key"))


def duplicate_contract_failures(routes: list[object]) -> list[str]:
    contract_ids: dict[str, str] = {}
    failures: list[str] = []
    for row in routes:
        claim = contract_claim(row)
        if claim is None:
            continue
        contract_id, key = claim
        if contract_id in contract_ids:
            failures.append(
                f"duplicate-contract: {contract_id} is claimed by {contract_ids[contract_id]} and "
                f"{key}; the derivation must yield one contract per route"
            )
        else:
            contract_ids[contract_id] = key
    return failures
