"""Multi-label write-path validation and resolution (milestone 3.C.4)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.exceptions import ValidationError
from app.schemas.limits import MAX_LABELS

VALID_LABELS = frozenset(
    {"factual", "preference", "behavioral", "episodic", "procedural"}
)


@dataclass(frozen=True, slots=True)
class MemoryLabelInput:
    label: str
    confidence: float


@dataclass(frozen=True, slots=True)
class LabelInsert:
    org_id: UUID
    memory_id: UUID
    label: str
    confidence: float


def _validate_label_taxonomy(label: str, *, index: int | None = None) -> None:
    if label not in VALID_LABELS:
        field = "labels" if index is None else f"labels[{index}].label"
        raise ValidationError(
            f"Invalid label: {label}",
            field=field,
            field_code="invalid_label",
        )


def _validate_confidence(confidence: float, *, index: int | None = None) -> None:
    if confidence < 0.0 or confidence > 1.0:
        field = "labels" if index is None else f"labels[{index}].confidence"
        raise ValidationError(
            "Confidence must be between 0.0 and 1.0",
            field=field,
            field_code="confidence_out_of_range",
        )


def validate_write_labels(labels: Sequence[MemoryLabelInput]) -> None:
    """Validate resolved label list (count, taxonomy, confidence, duplicates)."""
    if len(labels) < 1:
        raise ValidationError(
            "At least one label is required",
            field="labels",
            field_code="labels_required",
        )
    if len(labels) > MAX_LABELS:
        raise ValidationError(
            f"At most {MAX_LABELS} labels allowed",
            field="labels",
            field_code="too_many_labels",
        )
    seen: set[str] = set()
    for index, item in enumerate(labels):
        _validate_label_taxonomy(item.label, index=index)
        _validate_confidence(item.confidence, index=index)
        if item.label in seen:
            raise ValidationError(
                "Duplicate label in request",
                field="labels",
                field_code="duplicate_label",
            )
        seen.add(item.label)


def resolve_write_labels(
    *,
    category: str,
    confidence: float,
    labels: Sequence[MemoryLabelInput] | None,
) -> tuple[MemoryLabelInput, ...]:
    """Resolve authoritative labels for a write; synthesize from scalar when omitted."""
    if labels is None:
        resolved = (MemoryLabelInput(label=category, confidence=confidence),)
        _validate_label_taxonomy(category)
        _validate_confidence(confidence)
        return resolved
    if len(labels) == 0:
        raise ValidationError(
            "At least one label is required",
            field="labels",
            field_code="labels_required",
        )
    validate_write_labels(labels)
    return tuple(labels)


def labels_from_command(
    org_id: UUID,
    memory_id: UUID,
    labels: tuple[MemoryLabelInput, ...],
) -> list[LabelInsert]:
    return [
        LabelInsert(
            org_id=org_id,
            memory_id=memory_id,
            label=item.label,
            confidence=item.confidence,
        )
        for item in labels
    ]
