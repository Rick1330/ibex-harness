"""Unit tests for the export_openapi output-path guard (S8707)."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "export_openapi.py"
_REPO_SNAPSHOT = _SCRIPT.resolve().parents[1] / "openapi.snapshot.json"


@pytest.fixture
def resolve_output_path():
    spec = importlib.util.spec_from_file_location("export_openapi", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.resolve_output_path


def test_accepts_repo_snapshot_path(resolve_output_path) -> None:
    resolved = resolve_output_path(_REPO_SNAPSHOT)
    assert resolved == _REPO_SNAPSHOT


def test_accepts_temp_directory_paths(resolve_output_path, tmp_path: Path) -> None:
    resolved = resolve_output_path(tmp_path / "scratch.json")
    assert resolved == (tmp_path / "scratch.json").resolve()


@pytest.mark.parametrize(
    "bad",
    [
        "/etc/evil.json",
        str(_SCRIPT.parent / "other.json"),
        str(_SCRIPT.parent / "app" / "evil.json"),
    ],
)
def test_rejects_paths_outside_allowed_roots(resolve_output_path, bad: str) -> None:
    with pytest.raises(SystemExit, match="output path must be"):
        resolve_output_path(bad)


def test_rejects_dotdot_traversal_outside_roots(resolve_output_path) -> None:
    traversal = Path(tempfile.gettempdir()) / "sub" / ".." / ".." / "etc" / "evil.json"
    with pytest.raises(SystemExit, match="output path must be"):
        resolve_output_path(traversal)


def test_rejects_symlinks_pointing_outside_roots(resolve_output_path, tmp_path: Path) -> None:
    outside = _SCRIPT.parent / "app" / "openapi-target.json"
    link = tmp_path / "link.json"
    link.symlink_to(outside)
    try:
        with pytest.raises(SystemExit, match="output path must be"):
            resolve_output_path(link)
    finally:
        link.unlink()
