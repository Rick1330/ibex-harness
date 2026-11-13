"""Tests for the REST deprecation header emitter (P1-01).

The record is read once when the application is constructed, so every test injects its own
temporary record through ``ApiRuntimeOverrides`` and never touches the committed one. The
committed record is asserted on its own: it is empty, so the emitter must add nothing.

``GET /v1/operator/session/me`` is the deprecated route in the harness (contract
``operator.session.me.v1``, ``beta``) and ``GET /v1/agents/{agent_id}`` proves the route is
resolved from the matched template rather than the request path. Neither needs PostgreSQL: the
route answers with a 503 envelope and the headers are attached either way, which is the point —
the notice belongs to the response, not to a successful one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from app.config import Settings
from app.main import ApiRuntimeOverrides, create_app
from app.middleware.deprecations import load_deprecation_headers

_REPO_ROOT = Path(__file__).resolve().parents[4]
_REST_REGISTRY = _REPO_ROOT / "engineering/architecture-v2/contracts/rest-route-registry.json"
_DEPRECATED_ROUTE = "/v1/operator/session/me"
_DEPRECATED_CONTRACT = "operator.session.me.v1"
_EVIDENCE = "engineering/architecture-v2/16-compatibility-and-versioning.md"
# 2026-01-02 and 2099-12-31 as the wire values: an RFC 9651 Date and an RFC 8594 HTTP-date.
_DEPRECATION_VALUE = "@1767312000"
_SUNSET_VALUE = "Thu, 31 Dec 2099 00:00:00 GMT"


def _entry(**overrides: Any) -> dict[str, Any]:
    """A valid ``announced`` REST entry for ``operator.session.me.v1``."""
    entry: dict[str, Any] = {
        "id": "dep-1",
        "surface": "rest",
        "stability": "beta",
        "notice_date": "2026-01-01",
        "sunset_date": "2099-12-31",
        "status": "announced",
        "successor": "operator.session.me.v2",
        "headers_implemented": True,
        "evidence": _EVIDENCE,
        "contract_id": _DEPRECATED_CONTRACT,
        "announced_on": "2026-01-02",
    }
    entry.update(overrides)
    return entry


def _record(tmp_path: Path, *entries: dict[str, Any]) -> Path:
    path = tmp_path / "deprecations.json"
    payload = {"schema": "ibex.deprecations.v1", "entries": list(entries)}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _application(record: Path | None) -> FastAPI:
    """The real application, with the deprecation record injected (``None`` = committed)."""
    runtime = ApiRuntimeOverrides(deprecation_record=record, deprecation_registry=_REST_REGISTRY)
    return create_app(settings=Settings(database_url=None), runtime=runtime)


def _app(record: Path | None) -> TestClient:
    return TestClient(_application(record))


def _headers_for(record: Path | None, path: str) -> Response:
    with _app(record) as client:
        return client.get(path)


def _mounted(record: Path | None) -> list[str]:
    return [middleware.cls.__name__ for middleware in _application(record).user_middleware]


def _assert_no_deprecation_headers(response: Response) -> None:
    assert "deprecation" not in response.headers
    assert "sunset" not in response.headers


def test_deprecated_route_emits_both_headers(tmp_path: Path) -> None:
    response = _headers_for(_record(tmp_path, _entry()), _DEPRECATED_ROUTE)
    assert response.headers["deprecation"] == _DEPRECATION_VALUE
    assert response.headers["sunset"] == _SUNSET_VALUE


def test_route_without_a_deprecated_contract_emits_nothing(tmp_path: Path) -> None:
    response = _headers_for(_record(tmp_path, _entry()), "/health")
    assert response.status_code == 200
    _assert_no_deprecation_headers(response)


def test_entry_that_does_not_declare_the_headers_emits_nothing(tmp_path: Path) -> None:
    record = _record(tmp_path, _entry(headers_implemented=False))
    _assert_no_deprecation_headers(_headers_for(record, _DEPRECATED_ROUTE))


def test_mcp_entry_is_ignored(tmp_path: Path) -> None:
    mcp = {
        "id": "dep-mcp",
        "surface": "mcp",
        "stability": "beta",
        "notice_date": "2026-01-01",
        "sunset_date": "2099-12-31",
        "status": "announced",
        "successor": "budget.read",
        "headers_implemented": False,
        "evidence": _EVIDENCE,
        "tool": "budget.get",
        "server": "operator",
        "announced_on": "2026-01-02",
    }
    record = _record(tmp_path, mcp)
    loaded = load_deprecation_headers(record=record, registry=_REST_REGISTRY)
    assert loaded.failures == ()
    assert dict(loaded.routes) == {}
    _assert_no_deprecation_headers(_headers_for(record, _DEPRECATED_ROUTE))


def test_route_resolution_uses_the_matched_template_not_the_request_path(tmp_path: Path) -> None:
    """The registry key is ``GET /v1/agents/{agent_id}``, which no concrete path equals."""
    entry = _entry(
        id="dep-agents",
        stability="stable",
        contract_id="management.agents.get.v1",
        successor="management.agents.get.v2",
    )
    response = _headers_for(_record(tmp_path, entry), f"/v1/agents/{uuid4()}")
    assert response.headers["deprecation"] == _DEPRECATION_VALUE


def test_committed_record_emits_nothing() -> None:
    """The 1.0 state: an empty record adds no header and loads no failure."""
    loaded = load_deprecation_headers()
    assert loaded.failures == ()
    assert dict(loaded.routes) == {}
    _assert_no_deprecation_headers(_headers_for(None, _DEPRECATED_ROUTE))


def test_middleware_is_mounted_only_when_a_route_is_deprecated(tmp_path: Path) -> None:
    """The empty record leaves the middleware stack unchanged: no hop and no lookup."""
    assert "DeprecationHeadersMiddleware" not in _mounted(None)
    assert "DeprecationHeadersMiddleware" in _mounted(_record(tmp_path, _entry()))


def test_cors_exposes_the_deprecation_headers() -> None:
    """A cross-origin consumer can only read a header the CORS layer exposes."""
    with _app(None) as client:
        response = client.get("/health", headers={"Origin": "http://localhost:3100"})
    assert response.headers["access-control-expose-headers"] == (
        "X-Request-ID, X-IBEX-Drain, Deprecation, Sunset"
    )


def test_past_sunset_is_skipped_not_fatal(tmp_path: Path) -> None:
    expired = _entry(
        id="dep-expired",
        notice_date="2019-01-01",
        announced_on="2019-01-02",
        sunset_date="2020-01-01",
    )
    record = _record(tmp_path, expired)
    loaded = load_deprecation_headers(record=record, registry=_REST_REGISTRY)
    assert loaded.failures == ()
    assert dict(loaded.routes) == {}
    _assert_no_deprecation_headers(_headers_for(record, _DEPRECATED_ROUTE))


def test_expired_entry_does_not_silence_a_live_one(tmp_path: Path) -> None:
    expired = _entry(
        id="dep-expired",
        stability="stable",
        contract_id="management.agents.get.v1",
        successor="management.agents.get.v2",
        notice_date="2019-01-01",
        announced_on="2019-01-02",
        sunset_date="2020-01-01",
    )
    live = _entry(id="dep-live")
    loaded = load_deprecation_headers(
        record=_record(tmp_path, expired, live), registry=_REST_REGISTRY
    )
    assert loaded.failures == ()
    assert set(loaded.routes) == {f"GET {_DEPRECATED_ROUTE}"}


def test_missing_record_fails_closed(tmp_path: Path) -> None:
    loaded = load_deprecation_headers(record=tmp_path / "absent.json", registry=_REST_REGISTRY)
    assert dict(loaded.routes) == {}
    assert loaded.failures and loaded.failures[0].startswith("missing-record:")


def test_invalid_json_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "deprecations.json"
    path.write_text("{", encoding="utf-8")
    loaded = load_deprecation_headers(record=path, registry=_REST_REGISTRY)
    assert dict(loaded.routes) == {}
    assert any(failure.startswith("invalid-record:") for failure in loaded.failures)


def test_wrong_schema_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "deprecations.json"
    path.write_text(json.dumps({"schema": "ibex.deprecations.v2", "entries": []}), encoding="utf-8")
    loaded = load_deprecation_headers(record=path, registry=_REST_REGISTRY)
    assert loaded.failures == (
        "unknown-enum: record schema is 'ibex.deprecations.v2'; expected 'ibex.deprecations.v1'",
    )


def test_malformed_entry_fails_the_whole_record_closed(tmp_path: Path) -> None:
    """One broken entry makes the record untrusted, so the live entry emits nothing either."""
    broken = _entry(id="dep-broken")
    del broken["headers_implemented"]
    record = _record(tmp_path, broken, _entry(id="dep-live"))
    loaded = load_deprecation_headers(record=record, registry=_REST_REGISTRY)
    assert dict(loaded.routes) == {}
    assert any(
        failure.startswith("invalid-field: dep-broken.headers_implemented")
        for failure in loaded.failures
    )
    _assert_no_deprecation_headers(_headers_for(record, _DEPRECATED_ROUTE))


def test_two_live_entries_for_one_contract_fail_closed(tmp_path: Path) -> None:
    """The emitter must not resolve the contradiction by keeping the last entry."""
    record = _record(tmp_path, _entry(id="dep-1"), _entry(id="dep-2", sunset_date="2099-06-30"))
    loaded = load_deprecation_headers(record=record, registry=_REST_REGISTRY)
    assert dict(loaded.routes) == {}
    assert any(failure.startswith("duplicate-contract:") for failure in loaded.failures)


def test_unsorted_entries_fail_closed(tmp_path: Path) -> None:
    record = _record(tmp_path, _entry(id="dep-2"), _entry(id="dep-1", sunset_date="2099-06-30"))
    loaded = load_deprecation_headers(record=record, registry=_REST_REGISTRY)
    assert dict(loaded.routes) == {}
    assert any(failure.startswith("unsorted-record:") for failure in loaded.failures)


def test_missing_registry_fails_closed(tmp_path: Path) -> None:
    loaded = load_deprecation_headers(
        record=_record(tmp_path, _entry()), registry=tmp_path / "absent.json"
    )
    assert dict(loaded.routes) == {}
    assert loaded.failures and loaded.failures[0].startswith("missing-rest-registry:")
