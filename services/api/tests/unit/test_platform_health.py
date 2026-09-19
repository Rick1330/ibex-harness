"""Unit tests for operator platform health (4.P.5)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.errors import ApiError
from app.routers.platform import (
    _load_drill,
    _parse_backup_stamp,
    platform_health,
)


def test_parse_backup_stamp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stamp = tmp_path / "ibex-last-backup.txt"
    stamp.write_text("[backup] ok 2026-09-19T07:00:00+00:00\n", encoding="utf-8")
    monkeypatch.setattr("app.routers.platform._BACKUP_STAMP", stamp)
    got = _parse_backup_stamp()
    assert got == datetime(2026, 9, 19, 7, 0, tzinfo=UTC)


def test_load_drill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = tmp_path / "restore-drill-report.json"
    report.write_text(json.dumps({"milestone": "4.P.5", "ok": True}), encoding="utf-8")
    monkeypatch.setattr("app.routers.platform._DRILL_REPORT", report)
    assert _load_drill()["milestone"] == "4.P.5"


@pytest.mark.asyncio
async def test_platform_health_disabled() -> None:
    req = MagicMock()
    req.app.state.settings = MagicMock(operator_feature_enabled=False)
    with pytest.raises(ApiError) as exc:
        await platform_health(req)
    assert "operator feature disabled" in str(exc.value)


@pytest.mark.asyncio
async def test_platform_health_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_DLQ_DEPTH", "3")
    monkeypatch.setenv("IBEX_DEPLOY_IMAGE_DIGEST", "sha256:abc")
    req = MagicMock()
    req.app.state.settings = MagicMock(
        operator_feature_enabled=True,
        redis_url="redis://localhost:6379/0",
        platform_retention_horizon_days=90,
    )
    api = MagicMock()
    api.ready = True
    api.validator = object()
    api.session_factory = None
    api.drain = MagicMock(is_draining=lambda: False)
    req.app.state.api = api
    out = await platform_health(req)
    assert out.dlq_depth == 3
    assert out.deploy_image_digest == "sha256:abc"
    assert out.dependency_health["api"] == "ok"
    # session_factory None ⇒ postgres unavailable ⇒ degraded_mode true
    assert out.dependency_health["postgres"] == "unavailable"
    assert out.degraded_mode is True
