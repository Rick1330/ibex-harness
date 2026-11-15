from __future__ import annotations

import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from _enqueue_http_test_helpers import (
    _claim_header,
    _client,
    _enqueue_headers,
    _ledger,
    _post_enqueue,
    _settings,
    _valid_body,
    reset_enqueue_state,
)
from starlette.testclient import TestClient

from app.enqueue_http import MAX_ENQUEUE_BODY_BYTES, create_enqueue_app


@pytest.fixture(autouse=True)
def _reset_enqueue_state() -> None:
    reset_enqueue_state()

def test_enqueue_rejects_missing_and_bad_bearer() -> None:
    calls: list[dict] = []
    client = _client(apply_async=lambda kwargs: calls.append(kwargs) or SimpleNamespace(id="t1"))
    assert client.post("/internal/extraction/enqueue", json=_valid_body()).status_code == 401
    assert _post_enqueue(client, _valid_body(), token="wrong").status_code == 401
    assert calls == []


def test_enqueue_rejects_malformed_payload() -> None:
    client = _client(apply_async=lambda kwargs: SimpleNamespace(id="t1"))
    resp = _post_enqueue(client, {"org_id": "not-a-uuid", "turns": []})
    assert resp.status_code == 400


def test_enqueue_rejects_non_object_json() -> None:
    client = _client(apply_async=lambda kwargs: SimpleNamespace(id="t1"))
    resp = _post_enqueue(client, b"[1,2,3]", raw=True)
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_json"


@pytest.mark.parametrize(
    ("content_length", "expected_error"),
    [
        ("not-an-int", "invalid_content_length"),
        (str(MAX_ENQUEUE_BODY_BYTES + 1), "payload_too_large"),
    ],
)
def test_enqueue_rejects_invalid_or_oversized_content_length(
    content_length: str, expected_error: str
) -> None:
    client = _client(apply_async=lambda kwargs: SimpleNamespace(id="t1"))
    headers = {
        "Authorization": "Bearer sekrit",
        "Content-Type": "application/json",
        "Content-Length": content_length,
    }
    resp = client.post("/internal/extraction/enqueue", headers=headers, content=b"{}")
    assert resp.status_code == 400
    assert resp.json()["error"] == expected_error


def test_enqueue_valid_claim_with_matching_body_accepts() -> None:
    captured: list[dict] = []

    def capture(kwargs: dict) -> SimpleNamespace:
        captured.append(kwargs)
        return SimpleNamespace(id="task-abc")

    body = _valid_body()
    resp = _post_enqueue(_client(apply_async=capture), body)
    assert resp.status_code == 202
    assert resp.json()["task_id"] == "task-abc"
    assert captured[0]["org_id"] == body["org_id"]
    assert captured[0]["turns"][0]["role"] == "user"


def test_enqueue_rejects_missing_claim() -> None:
    calls: list[dict] = []
    client = _client(apply_async=lambda kwargs: calls.append(kwargs) or SimpleNamespace(id="t1"))
    resp = _post_enqueue(client, _valid_body(), claim=None)
    assert resp.status_code == 403
    assert resp.json() == {"error": "claim_required"}
    assert calls == []


@pytest.mark.parametrize("field", ["org_id", "agent_id", "session_id"])
def test_enqueue_rejects_body_naming_a_different_tenant(field: str) -> None:
    """A body that disagrees with the signed claim is refused before any tenant work."""
    calls: list[dict] = []
    client = _client(apply_async=lambda kwargs: calls.append(kwargs) or SimpleNamespace(id="t1"))
    body = _valid_body()
    claimed = _valid_body()
    resp = _post_enqueue(client, body, claim=_claim_header(claimed))
    assert resp.status_code == 403
    assert resp.json() == {"error": "claim_scope_mismatch"}
    assert calls == []
    assert _ledger.records == {}
    assert str(body[field]) not in resp.text
    assert str(claimed[field]) not in resp.text


def test_enqueue_rejects_expired_claim() -> None:
    calls: list[dict] = []
    client = _client(apply_async=lambda kwargs: calls.append(kwargs) or SimpleNamespace(id="t1"))
    body = _valid_body()
    resp = _post_enqueue(client, body, exp=int(time.time()) - 3600)
    assert resp.status_code == 403
    assert resp.json() == {"error": "claim_expired"}
    assert calls == []


def test_enqueue_tolerates_small_clock_skew_on_expiry() -> None:
    body = _valid_body()
    client = _client(apply_async=lambda kwargs: SimpleNamespace(id="skewed"))
    resp = _post_enqueue(client, body, exp=int(time.time()) - 2)
    assert resp.status_code == 202


def test_enqueue_rejects_tampered_mac() -> None:
    calls: list[dict] = []
    client = _client(apply_async=lambda kwargs: calls.append(kwargs) or SimpleNamespace(id="t1"))
    body = _valid_body()
    claim = _claim_header(body)
    tampered = claim[:-1] + ("1" if claim[-1] != "1" else "0")
    resp = _post_enqueue(client, body, claim=tampered)
    assert resp.status_code == 403
    assert resp.json() == {"error": "claim_invalid"}
    assert calls == []


def test_enqueue_rejects_claim_signed_with_another_secret() -> None:
    body = _valid_body()
    client = _client(apply_async=lambda kwargs: SimpleNamespace(id="t1"))
    resp = _post_enqueue(client, body, claim=_claim_header(body, secret="not-the-token"))
    assert resp.status_code == 403
    assert resp.json() == {"error": "claim_invalid"}


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda c: c.replace("v1:", "v2:", 1), id="bad-version"),
        pytest.param(lambda c: c.rsplit(":", 1)[0], id="missing-mac"),
        pytest.param(lambda c: c + ":extra", id="extra-field"),
        pytest.param(lambda c: "", id="empty"),
    ],
)
def test_enqueue_rejects_malformed_claim(mutate) -> None:
    body = _valid_body()
    client = _client(apply_async=lambda kwargs: SimpleNamespace(id="t1"))
    resp = _post_enqueue(client, body, claim=mutate(_claim_header(body)))
    assert resp.status_code == 403


def test_enqueue_rejects_non_numeric_exp_with_valid_mac() -> None:
    body = _valid_body()
    client = _client(apply_async=lambda kwargs: SimpleNamespace(id="t1"))
    resp = _post_enqueue(client, body, claim=_claim_header(body, exp="not-a-number"))
    assert resp.status_code == 403
    assert resp.json() == {"error": "claim_invalid"}


def test_enqueue_rejects_claim_ids_edited_after_signing() -> None:
    """The MAC covers the ids, so editing them in the payload is rejected."""
    body = _valid_body()
    other_org = str(uuid4())
    claim = _claim_header(body)
    parts = claim.split(":")
    parts[1] = other_org
    client = _client(apply_async=lambda kwargs: SimpleNamespace(id="t1"))
    resp = _post_enqueue(client, body, claim=":".join(parts))
    assert resp.status_code == 403
    assert resp.json() == {"error": "claim_invalid"}


def test_enqueue_requires_explicit_key_and_durable_ledger() -> None:
    body = _valid_body()
    client = TestClient(
        create_enqueue_app(_settings(), apply_async=lambda _: SimpleNamespace(id="x"))
    )
    no_key_headers = _enqueue_headers(body)
    del no_key_headers["Idempotency-Key"]
    missing_key = client.post(
        "/internal/extraction/enqueue",
        headers=no_key_headers,
        json=body,
    )
    assert missing_key.status_code == 400
    assert missing_key.json() == {"error": "idempotency_key_required"}
    no_ledger = TestClient(
        create_enqueue_app(_settings(), apply_async=lambda _: SimpleNamespace(id="x"), ledger=None)
    )
    unavailable = no_ledger.post(
        "/internal/extraction/enqueue",
        headers=_enqueue_headers(body),
        json=body,
    )
    assert unavailable.status_code == 503
    assert unavailable.json() == {"error": "idempotency_unavailable"}


def test_enqueue_rejects_overlong_key_before_claim() -> None:
    body = _valid_body()
    response = _client(apply_async=lambda _: SimpleNamespace(id="must-not-run")).post(
        "/internal/extraction/enqueue",
        headers=_enqueue_headers(body, key="x" * 257),
        json=body,
    )
    assert response.status_code == 400
    assert response.json() == {"error": "idempotency_key_too_long"}


def test_enqueue_rejects_empty_and_bad_json_body() -> None:
    client = _client(apply_async=lambda kwargs: SimpleNamespace(id="t1"))
    empty = client.post(
        "/internal/extraction/enqueue",
        headers={"Authorization": "Bearer sekrit", "Content-Type": "application/json"},
        content=b"",
    )
    assert empty.status_code == 400
    bad = _post_enqueue(client, b"{not-json", raw=True)
    assert bad.status_code == 400
    assert bad.json()["error"] == "invalid_json"


def test_enqueue_rejects_missing_org_id() -> None:
    body = _valid_body()
    del body["org_id"]
    resp = _post_enqueue(_client(apply_async=lambda kwargs: SimpleNamespace(id="t1")), body)
    assert resp.status_code == 400


def test_bearer_length_mismatch_and_empty_expected() -> None:
    from app.enqueue_http import _bearer_matches

    assert _bearer_matches("a", "") is False
    assert _bearer_matches("ab", "a") is False
    assert _bearer_matches("same", "same") is True


@pytest.mark.asyncio
async def test_read_json_limited_stream_cap_and_no_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from starlette.requests import Request

    from app import enqueue_http as mod

    monkeypatch.setattr(mod, "MAX_ENQUEUE_BODY_BYTES", 8)

    async def receive():
        return {"type": "http.request", "body": b'{"a":1,"pad":true}', "more_body": False}

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1),
        "server": ("127.0.0.1", 80),
    }
    req = Request(scope, receive)
    mod._check_content_length(req)
    with pytest.raises(ValueError, match="payload_too_large"):
        await mod._read_json_limited(req)


def _db_settings(**overrides: object) -> SimpleNamespace:
    """Settings that make ``create_enqueue_app`` build its own ledger."""
    settings = _settings(**overrides)
    settings.database_url = "postgresql+asyncpg://worker@db/ibex"
    return settings


class _ScopeEntered(Exception):
    """Sentinel proving the claim entered the injected session scope."""


class _ScopeRecorder:
    """Async context manager factory that records each call and stops there."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, org_id: str):
        self.calls.append(org_id)
        return self._cm()

    @asynccontextmanager
    async def _cm(self):
        raise _ScopeEntered()
        yield  # pragma: no cover - the scope never yields in this test


def test_create_enqueue_app_injects_pinned_ledger_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production construction site hands the ledger both pinned scopes."""
    from app import enqueue_http as mod

    org_scope, probe_scope = object(), object()
    captured: dict[str, object] = {}

    class _SpyLedger:
        def __init__(self, factory, *, session_scope=None, probe_scope=None):
            captured["factory"] = factory
            captured["session_scope"] = session_scope
            captured["probe_scope"] = probe_scope

    monkeypatch.setattr(mod, "create_engine", lambda _settings: "engine")
    monkeypatch.setattr(mod, "create_session_factory", lambda engine: ("factory", engine))
    monkeypatch.setattr(mod, "app_org_scope", lambda factory: org_scope)
    monkeypatch.setattr(mod, "app_probe_scope", lambda factory: probe_scope)
    monkeypatch.setattr(mod, "PostgresIdempotencyLedger", _SpyLedger)

    app = mod.create_enqueue_app(_db_settings())

    assert captured == {
        "factory": ("factory", "engine"),
        "session_scope": org_scope,
        "probe_scope": probe_scope,
    }
    assert isinstance(app.state.ledger, _SpyLedger)


def test_claim_scope_comes_from_the_verified_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The claim's org enters the injected org scope; a body naming another tenant never does.

    This replaces the pre-S01 contract, which asserted that the *body's* org_id
    reached the scope — the defect itself. It now asserts the reverse: the scope
    is entered with the verified claim's org, and a body that disagrees with the
    claim is refused before the scope (and therefore before any tenant write).
    """
    from app import enqueue_http as mod
    from app.idempotency_ledger import PostgresIdempotencyLedger

    org_scope = _ScopeRecorder()
    probe_scope = _ScopeRecorder()
    monkeypatch.setattr(mod, "create_engine", lambda _settings: "engine")
    monkeypatch.setattr(mod, "create_session_factory", lambda _engine: "factory")
    monkeypatch.setattr(mod, "app_org_scope", lambda _factory: org_scope)
    monkeypatch.setattr(mod, "app_probe_scope", lambda _factory: probe_scope)

    app = mod.create_enqueue_app(_db_settings(), apply_async=lambda _: SimpleNamespace(id="x"))
    ledger = app.state.ledger
    assert isinstance(ledger, PostgresIdempotencyLedger)

    dispatched: list[dict] = []
    app.state.apply_async = lambda kwargs: dispatched.append(kwargs) or SimpleNamespace(id="x")
    client = TestClient(app)

    claim_org = uuid4()
    matching = _valid_body(org_id=str(claim_org))
    accepted = _post_enqueue(client, matching)
    # _ScopeEntered aborts the claim, which the surface reports as unavailable;
    # what matters is which org reached the scope before that.
    assert accepted.status_code == 503
    assert org_scope.calls == [str(claim_org)]
    assert probe_scope.calls == []

    org_scope.calls.clear()
    mismatched = _valid_body(org_id=str(uuid4()))
    refused = _post_enqueue(client, mismatched, claim=_claim_header(matching))
    assert refused.status_code == 403
    assert refused.json() == {"error": "claim_scope_mismatch"}
    assert org_scope.calls == []
    assert probe_scope.calls == []
    assert dispatched == []
