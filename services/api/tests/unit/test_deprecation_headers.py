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

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from starlette.types import Message, Receive, Scope, Send

from app.config import Settings
from app.main import ApiRuntimeOverrides, create_app
from app.middleware.deprecations import (
    DeprecationHeadersMiddleware,
    RouteNotice,
    load_deprecation_headers,
)

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


def _proxy_entry(**overrides: Any) -> dict[str, Any]:
    """A valid ``announced`` proxy entry: the proxy announces it, this emitter ignores it."""
    entry: dict[str, Any] = {
        "id": "dep-proxy",
        "surface": "proxy",
        "stability": "beta",
        "notice_date": "2026-01-01",
        "sunset_date": "2099-12-31",
        "status": "announced",
        "successor": "chat.completions.v2",
        "headers_implemented": True,
        "evidence": _EVIDENCE,
        "path": "/v1/chat/completions",
        "announced_on": "2026-01-02",
    }
    entry.update(overrides)
    return entry


def _record(tmp_path: Path, *entries: dict[str, Any]) -> Path:
    path = tmp_path / "deprecations.json"
    payload = {"schema": "ibex.deprecations.v1", "entries": list(entries)}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _json_file(tmp_path: Path, name: str, payload: object) -> Path:
    """Write ``payload`` as JSON under ``name``: a record or registry the module must judge."""
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _registry(tmp_path: Path, *rows: object) -> Path:
    """A registry whose ``routes`` are ``rows``, for shapes the committed registry cannot hold."""
    return _json_file(tmp_path, "registry.json", {"routes": list(rows)})


async def _unused_receive() -> Message:
    """A ``receive`` the middleware must never call: it reads no request body."""
    raise AssertionError("the deprecation middleware must not read the request body")


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


def test_announced_on_absent_falls_back_to_notice_date(tmp_path: Path) -> None:
    """``Deprecation`` carries the anchor the policy measures from: ``announced_on``, else notice."""
    record = _record(tmp_path, _entry(announced_on=None))
    loaded = load_deprecation_headers(record=record, registry=_REST_REGISTRY)
    assert loaded.failures == ()
    # 2026-01-01, the notice date: the entry records no announcement date of its own.
    assert _headers_for(record, _DEPRECATED_ROUTE).headers["deprecation"] == "@1767225600"


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


def test_proxy_entry_does_not_disable_rest_emission(tmp_path: Path) -> None:
    """A valid proxy entry is a record entry, not a broken one: REST keeps its headers.

    The surface enum here is the record's, not this emitter's. ``proxy`` used to be missing from
    it, so the first proxy deprecation failed the whole record closed and silenced every REST
    header with it.
    """
    record = _record(tmp_path, _entry(), _proxy_entry())
    loaded = load_deprecation_headers(record=record, registry=_REST_REGISTRY)
    assert loaded.failures == ()
    assert set(loaded.routes) == {f"GET {_DEPRECATED_ROUTE}"}
    response = _headers_for(record, _DEPRECATED_ROUTE)
    assert response.headers["deprecation"] == _DEPRECATION_VALUE
    assert response.headers["sunset"] == _SUNSET_VALUE


def test_proposed_entry_with_headers_declared_emits_nothing(tmp_path: Path) -> None:
    """The policy: both emitters act only on ``announced``. A plan is not a notice.

    The checker also rejects ``headers_implemented: true`` on a ``proposed`` entry, so this record
    could not be committed; the emitter still refuses it, because that gate is defence in depth
    and not the only guard.
    """
    announced = _entry(id="dep-1")
    proposed = _entry(
        id="dep-2",
        status="proposed",
        headers_implemented=True,
        announced_on=None,
        contract_id="management.agents.get.v1",
        successor="management.agents.get.v2",
    )
    record = _record(tmp_path, announced, proposed)
    loaded = load_deprecation_headers(record=record, registry=_REST_REGISTRY)
    assert loaded.failures == ()
    assert set(loaded.routes) == {f"GET {_DEPRECATED_ROUTE}"}
    with _app(record) as client:
        _assert_no_deprecation_headers(client.get(f"/v1/agents/{uuid4()}"))
        assert client.get(_DEPRECATED_ROUTE).headers["deprecation"] == _DEPRECATION_VALUE


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


def test_unmatched_route_emits_nothing(tmp_path: Path) -> None:
    """A 404 matched no route, so it resolves to no registry key and carries no notice."""
    response = _headers_for(_record(tmp_path, _entry()), "/v1/does-not-exist")
    assert response.status_code == 404
    _assert_no_deprecation_headers(response)


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


def test_route_headers_are_not_overwritten() -> None:
    """A header the route set itself wins: the middleware appends, never replaces."""
    existing = [(b"deprecation", b"@0"), (b"sunset", b"Mon, 01 Jan 2024 00:00:00 GMT")]

    async def route_app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": list(existing)})
        await send({"type": "http.response.body", "body": b""})

    declared = (
        (b"deprecation", _DEPRECATION_VALUE.encode("ascii")),
        (b"sunset", _SUNSET_VALUE.encode("ascii")),
    )
    notice = RouteNotice(headers=declared, sunset=date(2099, 12, 31))
    middleware = DeprecationHeadersMiddleware(route_app, {f"GET {_DEPRECATED_ROUTE}": notice})
    sent: list[Message] = []

    async def capture(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "method": "GET",
        "route": SimpleNamespace(path=_DEPRECATED_ROUTE),
    }
    asyncio.run(middleware(scope, _unused_receive, capture))
    assert sent[0]["headers"] == existing


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


def test_entry_without_a_sunset_date_is_skipped(tmp_path: Path) -> None:
    """The emitter cannot invent the removal date it is missing, so the entry emits nothing."""
    record = _record(tmp_path, _entry(sunset_date=""))
    loaded = load_deprecation_headers(record=record, registry=_REST_REGISTRY)
    assert loaded.failures == ()
    assert dict(loaded.routes) == {}
    _assert_no_deprecation_headers(_headers_for(record, _DEPRECATED_ROUTE))


def test_sunset_before_the_announcement_is_skipped(tmp_path: Path) -> None:
    """``Sunset`` never precedes ``Deprecation``: a notice that says so is not emitted."""
    record = _record(tmp_path, _entry(announced_on="2099-12-01", sunset_date="2099-06-30"))
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


def test_a_notice_stops_on_the_day_after_its_sunset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A process that starts inside a window must stop on its own when the window closes.

    The record is read once, so the sunset boundary travels with the notice and is
    rechecked against the current UTC day on every response. The sunset day itself still
    emits: the notice is good through the day it names.
    """
    today = datetime.now(UTC).date()
    record = _record(
        tmp_path,
        _entry(
            notice_date=(today - timedelta(days=1)).isoformat(),
            announced_on=(today - timedelta(days=1)).isoformat(),
            sunset_date=today.isoformat(),
        ),
    )
    with _app(record) as client:
        assert "deprecation" in client.get(_DEPRECATED_ROUTE).headers
        monkeypatch.setattr(
            "app.middleware.deprecations._utc_today", lambda: today + timedelta(days=1)
        )
        _assert_no_deprecation_headers(client.get(_DEPRECATED_ROUTE))


def test_missing_record_fails_closed(tmp_path: Path) -> None:
    loaded = load_deprecation_headers(record=tmp_path / "absent.json", registry=_REST_REGISTRY)
    assert dict(loaded.routes) == {}
    assert loaded.failures
    assert loaded.failures[0].startswith("missing-record:")


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
    assert loaded.failures
    assert loaded.failures[0].startswith("missing-rest-registry:")


def test_registry_without_a_routes_array_fails_closed(tmp_path: Path) -> None:
    """The registry's only route map is its ``routes`` array; without one nothing can resolve."""
    registry = _json_file(tmp_path, "registry.json", {"routes": {}})
    loaded = load_deprecation_headers(record=_record(tmp_path, _entry()), registry=registry)
    assert dict(loaded.routes) == {}
    assert loaded.failures == (f'missing-field: {registry} needs a "routes" array',)


def test_registry_row_that_is_not_an_object_fails_closed(tmp_path: Path) -> None:
    registry = _registry(tmp_path, f"GET {_DEPRECATED_ROUTE}")
    loaded = load_deprecation_headers(record=_record(tmp_path, _entry()), registry=registry)
    assert dict(loaded.routes) == {}
    assert loaded.failures == (
        f'invalid-route: {registry} routes[0] needs a "METHOD /path" key and a contract_id',
    )


def test_registry_row_without_a_contract_id_fails_closed(tmp_path: Path) -> None:
    registry = _registry(tmp_path, {"key": f"GET {_DEPRECATED_ROUTE}"})
    loaded = load_deprecation_headers(record=_record(tmp_path, _entry()), registry=registry)
    assert dict(loaded.routes) == {}
    assert loaded.failures == (
        f'invalid-route: {registry} routes[0] needs a "METHOD /path" key and a contract_id',
    )


def test_registry_key_without_a_path_fails_closed(tmp_path: Path) -> None:
    """A key must be ``"METHOD /path"``; a path that does not start with ``/`` is not a route."""
    registry = _registry(
        tmp_path, {"key": "GETv1/operator/session/me", "contract_id": _DEPRECATED_CONTRACT}
    )
    loaded = load_deprecation_headers(record=_record(tmp_path, _entry()), registry=registry)
    assert dict(loaded.routes) == {}
    assert loaded.failures == (
        f'invalid-route: {registry} routes[0] needs a "METHOD /path" key and a contract_id',
    )


def test_duplicate_registry_key_fails_closed(tmp_path: Path) -> None:
    """One key naming two contracts is a contradiction the emitter must not resolve."""
    key = f"GET {_DEPRECATED_ROUTE}"
    row = {"key": key, "contract_id": _DEPRECATED_CONTRACT}
    registry = _registry(tmp_path, row, dict(row))
    loaded = load_deprecation_headers(record=_record(tmp_path, _entry()), registry=registry)
    assert dict(loaded.routes) == {}
    assert loaded.failures == (f"duplicate-route: {registry} lists {key!r} more than once",)


def test_two_registry_keys_for_one_contract_both_emit(tmp_path: Path) -> None:
    """Every registry route whose contract is deprecated carries the notice."""
    legacy = "GET /v1/operator/session/legacy"
    registry = _registry(
        tmp_path,
        {"key": f"GET {_DEPRECATED_ROUTE}", "contract_id": _DEPRECATED_CONTRACT},
        {"key": legacy, "contract_id": _DEPRECATED_CONTRACT},
    )
    loaded = load_deprecation_headers(record=_record(tmp_path, _entry()), registry=registry)
    assert loaded.failures == ()
    expected = (
        (b"deprecation", _DEPRECATION_VALUE.encode("ascii")),
        (b"sunset", _SUNSET_VALUE.encode("ascii")),
    )
    assert {key: notice.headers for key, notice in loaded.routes.items()} == {
        f"GET {_DEPRECATED_ROUTE}": expected,
        legacy: expected,
    }


def test_record_without_an_entries_array_fails_closed(tmp_path: Path) -> None:
    path = _json_file(
        tmp_path, "deprecations.json", {"schema": "ibex.deprecations.v1", "entries": {}}
    )
    loaded = load_deprecation_headers(record=path, registry=_REST_REGISTRY)
    assert dict(loaded.routes) == {}
    assert loaded.failures == ('missing-field: record needs an "entries" array',)


def test_entry_that_is_not_an_object_fails_closed(tmp_path: Path) -> None:
    path = _json_file(
        tmp_path, "deprecations.json", {"schema": "ibex.deprecations.v1", "entries": ["dep-1"]}
    )
    loaded = load_deprecation_headers(record=path, registry=_REST_REGISTRY)
    assert dict(loaded.routes) == {}
    assert loaded.failures == ("invalid-entry: entries[0] is not a JSON object",)


@pytest.mark.parametrize("bad_id", ["", 7])
def test_entry_id_that_is_not_a_non_empty_string_fails_closed(
    tmp_path: Path, bad_id: object
) -> None:
    loaded = load_deprecation_headers(
        record=_record(tmp_path, _entry(id=bad_id)), registry=_REST_REGISTRY
    )
    assert dict(loaded.routes) == {}
    assert loaded.failures == ("invalid-field: entries[0].id must be a non-empty string",)


def test_rest_entry_without_a_contract_id_fails_closed(tmp_path: Path) -> None:
    """A REST entry names the contract it deprecates; without one no route can be resolved."""
    loaded = load_deprecation_headers(
        record=_record(tmp_path, _entry(contract_id="")), registry=_REST_REGISTRY
    )
    assert dict(loaded.routes) == {}
    assert loaded.failures == (
        "invalid-field: dep-1.contract_id must be a non-empty string on a rest entry",
    )


def test_unknown_stability_fails_closed(tmp_path: Path) -> None:
    loaded = load_deprecation_headers(
        record=_record(tmp_path, _entry(stability="experimental")), registry=_REST_REGISTRY
    )
    assert dict(loaded.routes) == {}
    assert loaded.failures == (
        "unknown-enum: dep-1 has stability 'experimental'; expected one of ['beta', 'stable']",
    )


def test_invalid_date_fails_closed(tmp_path: Path) -> None:
    loaded = load_deprecation_headers(
        record=_record(tmp_path, _entry(sunset_date="2099-13-01")), registry=_REST_REGISTRY
    )
    assert dict(loaded.routes) == {}
    assert loaded.failures == (
        "invalid-date: dep-1.sunset_date is '2099-13-01'; expected YYYY-MM-DD",
    )


def test_duplicate_id_fails_closed(tmp_path: Path) -> None:
    record = _record(
        tmp_path,
        _entry(id="dep-1"),
        _entry(
            id="dep-1",
            contract_id="management.agents.get.v1",
            successor="management.agents.get.v2",
        ),
    )
    loaded = load_deprecation_headers(record=record, registry=_REST_REGISTRY)
    assert dict(loaded.routes) == {}
    assert loaded.failures == ("duplicate-id: dep-1 appears more than once",)


def test_unreadable_record_fails_closed(tmp_path: Path) -> None:
    """A record that exists but cannot be read is a failure, not an empty record."""
    path = tmp_path / "deprecations.json"
    path.mkdir()
    loaded = load_deprecation_headers(record=path, registry=_REST_REGISTRY)
    assert dict(loaded.routes) == {}
    assert loaded.failures
    assert loaded.failures[0].startswith("unreadable-record:")


def test_deeply_nested_record_fails_closed(tmp_path: Path) -> None:
    """JSON nested past the decoder's recursion limit is invalid, not a crash."""
    path = tmp_path / "deprecations.json"
    path.write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")
    loaded = load_deprecation_headers(record=path, registry=_REST_REGISTRY)
    assert dict(loaded.routes) == {}
    assert loaded.failures == (f"invalid-record: {path}: JSON is nested too deeply to read",)


def test_record_that_is_not_a_json_object_fails_closed(tmp_path: Path) -> None:
    path = _json_file(tmp_path, "deprecations.json", [])
    loaded = load_deprecation_headers(record=path, registry=_REST_REGISTRY)
    assert dict(loaded.routes) == {}
    assert loaded.failures == (f"invalid-record: {path} must be a JSON object",)
