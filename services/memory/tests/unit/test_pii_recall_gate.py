"""Structured PII recall must strictly exceed the CI threshold."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def recall_structured(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    path = Path(__file__).resolve().parents[4] / "benchmarks/memory/pii/recall_structured.py"
    spec = importlib.util.spec_from_file_location("recall_structured", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class StubPiiService:
        missed_id: str | None = None

        def __init__(self, settings: SimpleNamespace) -> None:
            self.settings = settings

        def process(self, text: str) -> SimpleNamespace:
            findings = [
                SimpleNamespace(entity_type=row["entity"])
                for row in module.FIXTURES
                if row["text"] == text and row["id"] != self.missed_id
            ]
            return SimpleNamespace(findings=findings)

    monkeypatch.setattr(module, "PiiService", StubPiiService)
    monkeypatch.setattr(module, "Settings", lambda: SimpleNamespace(pii_spacy_model="stub"))
    return module


def test_recall_at_threshold_fails(
    recall_structured: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recall_structured.PiiService.missed_id = "email-1"
    output = tmp_path / "recall.json"
    monkeypatch.setattr(sys, "argv", ["recall_structured.py", "--output", str(output)])

    assert recall_structured.main() == 1

    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["n"] == 20
    assert result["hits"] == 19
    assert result["recall"] == 0.95
    assert result["pass"] is False
    assert result["misses"] == ["email-1: expected EMAIL_ADDRESS got []"]


def test_perfect_recall_passes(
    recall_structured: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "recall.json"
    monkeypatch.setattr(sys, "argv", ["recall_structured.py", "--output", str(output)])

    assert recall_structured.main() == 0

    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["n"] == 20
    assert result["hits"] == 20
    assert result["recall"] == 1.0
    assert result["pass"] is True
    assert result["misses"] == []
