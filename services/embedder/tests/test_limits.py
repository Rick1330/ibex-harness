"""Input limit and validation tests."""

from __future__ import annotations

import pytest

from app.backends.stub import StubBackend
from app.errors import BatchTooLargeError, EmptyBatchError, TextTooLongError
from app.limits import MAX_BATCH_TEXTS, MAX_TEXT_BYTES
from app.validate import validate_embed_input


def test_validate_embed_input_rejects() -> None:
    with pytest.raises(EmptyBatchError):
        validate_embed_input([])
    with pytest.raises(EmptyBatchError):
        validate_embed_input([""])
    with pytest.raises(BatchTooLargeError):
        validate_embed_input(["x"] * (MAX_BATCH_TEXTS + 1))
    with pytest.raises(TextTooLongError):
        validate_embed_input(["a" * (MAX_TEXT_BYTES + 1)])
    validate_embed_input(["ok", "fine"])


async def test_stub_rejects_invalid_batch() -> None:
    stub = StubBackend.for_profile("cpu")
    with pytest.raises(EmptyBatchError):
        await stub.embed([])
    with pytest.raises(TextTooLongError):
        await stub.embed(["x" * (MAX_TEXT_BYTES + 1)])
