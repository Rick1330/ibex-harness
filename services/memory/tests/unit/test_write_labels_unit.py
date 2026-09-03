"""Unit tests for multi-label write resolution (milestone 3.C.4)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.exceptions import ValidationError
from app.routers.memory_write_support import memory_command_from_request
from app.schemas.memories import CreateMemoryRequest, MemoryLabelSchema
from app.write.labels import (
    MemoryLabelInput,
    labels_from_command,
    resolve_write_labels,
)


def test_resolve_write_labels_synthesizes_from_category() -> None:
    resolved = resolve_write_labels(category="preference", confidence=0.75, labels=None)
    assert resolved == (MemoryLabelInput(label="preference", confidence=0.75),)


def test_resolve_write_labels_1_2_3() -> None:
    labels = (
        MemoryLabelInput(label="factual", confidence=0.9),
        MemoryLabelInput(label="behavioral", confidence=0.7),
        MemoryLabelInput(label="episodic", confidence=0.6),
    )
    resolved = resolve_write_labels(category="factual", confidence=0.5, labels=labels)
    assert resolved == labels


def test_resolve_write_labels_authoritative_over_category() -> None:
    labels = (MemoryLabelInput(label="procedural", confidence=0.85),)
    resolved = resolve_write_labels(category="factual", confidence=0.5, labels=labels)
    assert resolved[0].label == "procedural"


@pytest.mark.parametrize(
    ("labels", "field_code"),
    [
        ((), "labels_required"),
        (
            (MemoryLabelInput(label="invalid", confidence=0.5),),
            "invalid_label",
        ),
        (
            (MemoryLabelInput(label="factual", confidence=1.5),),
            "confidence_out_of_range",
        ),
        (
            (
                MemoryLabelInput(label="factual", confidence=0.8),
                MemoryLabelInput(label="factual", confidence=0.7),
            ),
            "duplicate_label",
        ),
    ],
)
def test_resolve_write_labels_rejects_invalid(
    labels: tuple[MemoryLabelInput, ...],
    field_code: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        resolve_write_labels(category="factual", confidence=0.8, labels=labels)
    assert exc_info.value.field_code == field_code


def test_resolve_write_labels_rejects_too_many() -> None:
    labels = (
        MemoryLabelInput(label="factual", confidence=0.5),
        MemoryLabelInput(label="preference", confidence=0.5),
        MemoryLabelInput(label="behavioral", confidence=0.5),
    )
    from unittest.mock import patch

    with patch("app.write.labels.MAX_LABELS", 2), pytest.raises(ValidationError) as exc_info:
        resolve_write_labels(category="factual", confidence=0.8, labels=labels)
    assert exc_info.value.field_code == "too_many_labels"


def test_resolve_write_labels_rejects_empty_explicit_list() -> None:
    with pytest.raises(ValidationError) as exc_info:
        resolve_write_labels(category="factual", confidence=0.8, labels=())
    assert exc_info.value.field_code == "labels_required"


def test_memory_command_from_request_legacy_backward_compat() -> None:
    org_id = uuid4()
    command = memory_command_from_request(
        CreateMemoryRequest(
            agent_id=uuid4(),
            content="legacy scalar category",
            category="behavioral",
            confidence=0.77,
        ),
        org_id,
    )
    assert command.labels == (MemoryLabelInput(label="behavioral", confidence=0.77),)
    assert command.category == "behavioral"


def test_memory_command_from_request_passes_temporal_and_caller_org() -> None:
    org_a = uuid4()
    org_b = uuid4()
    start = datetime(2026, 9, 1, tzinfo=UTC)
    end = datetime(2026, 9, 8, tzinfo=UTC)
    request = CreateMemoryRequest(
        agent_id=uuid4(),
        content="User prefers dark mode in the IDE",
        confidence=0.4,
        valid_from=start,
        valid_until=end,
    )
    command_a = memory_command_from_request(request, org_a)
    command_b = memory_command_from_request(request, org_b)
    assert command_a.org_id == org_a
    assert command_b.org_id == org_b
    assert command_a.valid_from == start
    assert command_a.valid_until == end
    assert command_a.confidence == 0.4


def test_memory_command_from_request_multi_label() -> None:
    org_id = uuid4()
    command = memory_command_from_request(
        CreateMemoryRequest(
            agent_id=uuid4(),
            content="multi label payload",
            category="factual",
            labels=[
                MemoryLabelSchema(label="behavioral", confidence=0.8),
                MemoryLabelSchema(label="factual", confidence=0.6),
            ],
        ),
        org_id,
    )
    assert len(command.labels) == 2
    assert command.category == "behavioral"


def test_resolve_write_labels_rejects_non_finite_confidence() -> None:
    with pytest.raises(ValidationError) as exc_info:
        resolve_write_labels(
            category="factual",
            confidence=float("nan"),
            labels=None,
        )
    assert exc_info.value.field_code == "confidence_out_of_range"


def test_resolve_write_labels_rejects_infinite_label_confidence() -> None:
    labels = (MemoryLabelInput(label="factual", confidence=float("inf")),)
    with pytest.raises(ValidationError) as exc_info:
        resolve_write_labels(
            category="factual",
            confidence=0.8,
            labels=labels,
        )
    assert exc_info.value.field_code == "confidence_out_of_range"
    assert exc_info.value.field == "labels[0].confidence"


def test_resolve_write_labels_rejects_invalid_scalar_category() -> None:
    with pytest.raises(ValidationError) as exc_info:
        resolve_write_labels(category="invalid", confidence=0.8, labels=None)
    assert exc_info.value.field_code == "invalid_label"
    assert exc_info.value.field == "labels"


def test_labels_from_command_maps_rows() -> None:
    org_id = uuid4()
    memory_id = uuid4()
    rows = labels_from_command(
        org_id,
        memory_id,
        (MemoryLabelInput(label="factual", confidence=0.7),),
    )
    assert len(rows) == 1
    assert rows[0].org_id == org_id
    assert rows[0].memory_id == memory_id
    assert rows[0].label == "factual"
    assert rows[0].confidence == 0.7


def test_persist_never_updates_category() -> None:
    persist_path = Path(__file__).resolve().parents[2] / "app" / "write" / "persist.py"
    source = persist_path.read_text(encoding="utf-8")
    assert "UPDATE ibex_core.memories" not in source
    assert "SET category" not in source
