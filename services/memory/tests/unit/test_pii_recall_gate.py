"""Structured PII recall must strictly exceed the CI threshold."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


_RECALL_SCRIPT = Path(__file__).resolve().parents[4] / "benchmarks/memory/pii/recall_structured.py"


@pytest.fixture
def resolve_output_path():
    """Load the harness module with real PiiService imports via the repo venv."""
    spec = importlib.util.spec_from_file_location("recall_structured_guard", _RECALL_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.resolve_output_path


def test_output_guard_accepts_temp_and_baseline(resolve_output_path, tmp_path: Path) -> None:
    temp_path = resolve_output_path(tmp_path / "out.json")
    assert temp_path.suffix == ".json"
    baseline = resolve_output_path(_RECALL_SCRIPT.with_name("recall_structured.json"))
    assert baseline.name == "recall_structured.json"


def test_output_guard_rejects_bad_suffix(resolve_output_path, tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="must end with .json"):
        resolve_output_path(tmp_path / "out.txt")


def test_output_guard_rejects_outside_roots(resolve_output_path) -> None:
    with pytest.raises(SystemExit, match="must resolve inside one of"):
        resolve_output_path(Path("/etc/evil.json"))


def test_output_guard_rejects_dotdot_traversal(resolve_output_path) -> None:
    # Escapes the baseline root into the repo tree: still outside both roots.
    traversal = _RECALL_SCRIPT.parent.parent.parent / "services" / "memory" / "evil.json"
    with pytest.raises(SystemExit, match="must resolve inside one of"):
        resolve_output_path(traversal)


def test_output_guard_rejects_symlink_escape(resolve_output_path, tmp_path: Path) -> None:
    outside = Path("/etc/evil.json")
    link = tmp_path / "link.json"
    link.symlink_to(outside)
    try:
        with pytest.raises(SystemExit, match="must resolve inside one of"):
            resolve_output_path(link)
    finally:
        link.unlink()


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
