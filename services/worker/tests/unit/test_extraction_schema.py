"""Unit tests for extraction schema v2 (milestone 3.5.B.1)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.extraction.prompt_v2 import EXTRACTION_SYSTEM_PROMPT_V2
from app.extraction.schema import (
    CONTENT_MAX_BYTES,
    CONTENT_MAX_LENGTH,
    CONTENT_MIN_LENGTH,
    MAX_MEMORIES_PER_TURN,
    VALID_LABELS,
    ExtractedMemory,
    ExtractedMemoryLabel,
    ExtractionResult,
)

FIXTURES = Path(__file__).parent / "fixtures" / "extraction_examples.jsonl"


def _load_examples() -> list[dict]:
    rows: list[dict] = []
    with FIXTURES.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


EXAMPLES = _load_examples()


def test_fixture_inventory_meets_milestone_thresholds() -> None:
    assert len(EXAMPLES) >= 50
    two_cat = sum(
        1
        for ex in EXAMPLES
        for mem in ex["result"]["memories"]
        if len(mem["categories"]) == 2
    )
    temporary = sum(1 for ex in EXAMPLES if ex["kind"] == "temporary")
    assert two_cat >= 10
    assert temporary >= 5


@pytest.mark.parametrize("example", EXAMPLES, ids=[e["id"] for e in EXAMPLES])
def test_extraction_result_round_trips_hand_crafted_examples(example: dict) -> None:
    parsed = ExtractionResult.model_validate(example["result"])
    assert isinstance(parsed, ExtractionResult)
    # Round-trip through JSON to ensure datetime serialization is stable.
    again = ExtractionResult.model_validate(parsed.model_dump(mode="json"))
    assert again == parsed


def test_multi_category_examples_preserve_independent_confidences() -> None:
    multi_memories = [
        mem
        for ex in EXAMPLES
        for mem in ExtractionResult.model_validate(ex["result"]).memories
        if len(mem.categories) == 2
    ]
    assert len(multi_memories) >= 10
    for mem in multi_memories:
        labels = [c.label for c in mem.categories]
        confidences = [c.confidence for c in mem.categories]
        assert len(set(labels)) == 2
        assert len(confidences) == 2
        assert all(0.0 <= c <= 1.0 for c in confidences)
        assert labels[0] in VALID_LABELS and labels[1] in VALID_LABELS
        # Independent fields: each category keeps its own confidence value.
        assert isinstance(mem.categories[0].confidence, float)
        assert isinstance(mem.categories[1].confidence, float)


def test_temporary_examples_parse_valid_until() -> None:
    temps = [ex for ex in EXAMPLES if ex["kind"] == "temporary"]
    assert len(temps) >= 5
    for ex in temps:
        result = ExtractionResult.model_validate(ex["result"])
        for mem in result.memories:
            assert mem.valid_until is not None
            assert mem.valid_from is not None
            assert mem.valid_until > mem.valid_from


def test_indefinite_examples_have_null_valid_until() -> None:
    indefinite = [
        mem
        for ex in EXAMPLES
        if ex["kind"] in {"single", "multi", "batch"}
        for mem in ExtractionResult.model_validate(ex["result"]).memories
    ]
    assert any(m.valid_until is None for m in indefinite)


@pytest.mark.parametrize(
    "valid_from,valid_until",
    [
        (
            datetime(2026, 9, 1, tzinfo=UTC),
            datetime(2026, 9, 1, tzinfo=UTC),
        ),
        (
            datetime(2026, 9, 2, tzinfo=UTC),
            datetime(2026, 9, 1, tzinfo=UTC),
        ),
    ],
)
def test_valid_until_not_after_valid_from_rejected(
    valid_from: datetime, valid_until: datetime
) -> None:
    with pytest.raises(ValidationError, match="valid_until"):
        ExtractedMemory.model_validate(
            {
                "content": "Temporary fact with invalid interval",
                "categories": [{"label": "factual", "confidence": 0.9}],
                "confidence": 0.9,
                "valid_from": valid_from,
                "valid_until": valid_until,
            }
        )


def test_valid_until_null_with_valid_from_accepted() -> None:
    mem = ExtractedMemory.model_validate(
        {
            "content": "Indefinite fact after a known start",
            "categories": [{"label": "factual", "confidence": 0.9}],
            "confidence": 0.9,
            "valid_from": datetime(2026, 9, 1, tzinfo=UTC),
            "valid_until": None,
        }
    )
    assert mem.valid_until is None


def test_unknown_category_label_rejected_with_clear_error() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ExtractionResult.model_validate(
            {
                "memories": [
                    {
                        "content": "Something with a bogus category",
                        "categories": [{"label": "sentiment", "confidence": 0.5}],
                        "confidence": 0.5,
                    }
                ]
            }
        )
    err_text = str(exc_info.value).lower()
    assert "sentiment" in err_text or "literal" in err_text or "category" in err_text


def test_duplicate_category_label_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        ExtractedMemory.model_validate(
            {
                "content": "Duplicate labels should fail closed",
                "categories": [
                    {"label": "factual", "confidence": 0.9},
                    {"label": "factual", "confidence": 0.8},
                ],
                "confidence": 0.85,
            }
        )


def test_more_than_ten_memories_rejected_not_silently_truncated() -> None:
    memories = [
        {
            "content": f"Memory number {i:02d} content here",
            "categories": [{"label": "factual", "confidence": 0.8}],
            "confidence": 0.8,
        }
        for i in range(MAX_MEMORIES_PER_TURN + 1)
    ]
    with pytest.raises(ValidationError, match="at most 10"):
        ExtractionResult.model_validate({"memories": memories})


def test_exactly_ten_memories_accepted() -> None:
    memories = [
        {
            "content": f"Memory number {i:02d} content here",
            "categories": [{"label": "preference", "confidence": 0.7}],
            "confidence": 0.7,
        }
        for i in range(MAX_MEMORIES_PER_TURN)
    ]
    result = ExtractionResult.model_validate({"memories": memories})
    assert len(result.memories) == MAX_MEMORIES_PER_TURN


def test_content_too_short_rejected() -> None:
    with pytest.raises(ValidationError):
        ExtractedMemory.model_validate(
            {
                "content": "ab",
                "categories": [{"label": "factual", "confidence": 0.5}],
                "confidence": 0.5,
            }
        )


def test_content_too_long_rejected() -> None:
    with pytest.raises(ValidationError):
        ExtractedMemory.model_validate(
            {
                "content": "x" * (CONTENT_MAX_LENGTH + 1),
                "categories": [{"label": "factual", "confidence": 0.5}],
                "confidence": 0.5,
            }
        )


def test_content_bounds_constants_match_write_path() -> None:
    assert CONTENT_MIN_LENGTH == 5
    assert CONTENT_MAX_LENGTH == 10_000
    assert CONTENT_MAX_BYTES == 10_000


def test_multibyte_content_at_utf8_byte_limit_accepted() -> None:
    content = "é" * (CONTENT_MAX_BYTES // 2)
    assert len(content) < CONTENT_MAX_LENGTH
    assert len(content.encode("utf-8")) == CONTENT_MAX_BYTES
    mem = ExtractedMemory.model_validate(
        {
            "content": content,
            "categories": [{"label": "factual", "confidence": 0.5}],
            "confidence": 0.5,
        }
    )
    assert mem.content == content


def test_multibyte_content_over_utf8_byte_limit_rejected() -> None:
    content = "é" * (CONTENT_MAX_BYTES // 2 + 1)
    assert len(content) <= CONTENT_MAX_LENGTH
    assert len(content.encode("utf-8")) > CONTENT_MAX_BYTES
    with pytest.raises(ValidationError, match="UTF-8 bytes"):
        ExtractedMemory.model_validate(
            {
                "content": content,
                "categories": [{"label": "factual", "confidence": 0.5}],
                "confidence": 0.5,
            }
        )


def test_mixed_naive_and_aware_datetimes_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone-aware or both naive"):
        ExtractedMemory.model_validate(
            {
                "content": "Mixed timezone representations are invalid",
                "categories": [{"label": "factual", "confidence": 0.9}],
                "confidence": 0.9,
                "valid_from": datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC).replace(tzinfo=None),
                "valid_until": datetime(2026, 9, 2, 0, 0, 0, tzinfo=UTC),
            }
        )


def test_empty_memories_list_allowed() -> None:
    result = ExtractionResult.model_validate({"memories": []})
    assert result.memories == []


def test_prompt_v2_includes_multi_label_and_temporal_rules() -> None:
    assert "1–3 categories" in EXTRACTION_SYSTEM_PROMPT_V2 or "1-3" in EXTRACTION_SYSTEM_PROMPT_V2
    assert "valid_until" in EXTRACTION_SYSTEM_PROMPT_V2
    assert "timezone-aware ISO-8601" in EXTRACTION_SYSTEM_PROMPT_V2
    assert "10000 UTF-8 bytes" in EXTRACTION_SYSTEM_PROMPT_V2
    for label in sorted(VALID_LABELS):
        assert label in EXTRACTION_SYSTEM_PROMPT_V2


def test_extracted_memory_label_maps_to_write_path_shape() -> None:
    label = ExtractedMemoryLabel.model_validate(
        {"label": "preference", "confidence": 0.77}
    )
    dumped = label.model_dump()
    assert set(dumped.keys()) == {"label", "confidence"}
    assert dumped["label"] == "preference"
    assert dumped["confidence"] == 0.77


def test_strictly_after_interval_accepted() -> None:
    start = datetime(2026, 9, 1, tzinfo=UTC)
    mem = ExtractedMemory.model_validate(
        {
            "content": "Valid half-open style interval",
            "categories": [{"label": "episodic", "confidence": 0.8}],
            "confidence": 0.8,
            "valid_from": start,
            "valid_until": start + timedelta(hours=1),
        }
    )
    assert mem.valid_until is not None
    assert mem.valid_until > mem.valid_from  # type: ignore[operator]
