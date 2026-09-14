#!/usr/bin/env python3
"""Capture 4.P.0 smoke + rollback transcripts against an in-process API (TestClient).

Run from repo root:

  cd services/api && uv run python ../../web/engineering/research/operator-platform/4p0-smoke-transcript.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

API_ROOT = Path(__file__).resolve().parents[4] / "services" / "api"
sys.path.insert(0, str(API_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.auth.client import StaticTokenValidator, ValidateResult  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

# Long dummy secrets (≥32 bytes). Override via env in CI if needed.
_HMAC = os.environ.get(
    "JWT_HMAC_SECRET",
    "smoke-hmac-secret-material-32b-min!",
)
_CSRF = os.environ.get(
    "DASHBOARD_CSRF_SECRET",
    "smoke-csrf-secret-material-32b-min!",
)


def _fail(msg: str) -> None:
    raise SystemExit(f"SMOKE FAIL: {msg}")


def _engine() -> MagicMock:
    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)
    mock_engine.connect = MagicMock(return_value=mock_conn)
    return mock_engine


def _mask_login(body: dict) -> dict:
    out = dict(body)
    if "csrf_token" in out:
        out["csrf_token"] = "<redacted>"
    return out


def _step_login(client: TestClient) -> tuple[str, str]:
    print("\n# 1) POST /v1/operator/session/login")
    login = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_smoke"})
    print(f"HTTP {login.status_code}")
    print(_mask_login(login.json()))
    if login.status_code != 200:
        _fail(f"login HTTP {login.status_code}")
    body = login.json()
    return body["csrf_token"], body["org_id"]


def _step_me(client: TestClient) -> None:
    print("\n# 2) GET /v1/operator/session/me (cookie session)")
    me = client.get("/v1/operator/session/me")
    print(f"HTTP {me.status_code}")
    print(me.json())
    if me.status_code != 200 or me.json().get("auth") != "cookie":
        _fail("cookie /me failed")


def _step_publish(hub, org_id: str) -> None:
    print("\n# 3) Publish two operator events (in-process hub helper — no live /publish-test)")
    from uuid import UUID

    oid = UUID(org_id)
    for n in (1, 2):
        eid = asyncio.run(hub.publish({"n": n}, org_id=oid))
        print(f"publish n={n} → event_id={eid}")


def _step_sse_connect(client: TestClient, hub) -> int:
    print("\n# 4) SSE connect — finite subscribe mock (avoids hung stream)")

    async def sub_all(org_id, last_event_id=None):
        if last_event_id is not None:
            _fail("expected last_event_id None on first connect")
        for eid in (1, 2):
            yield f'id: {eid}\nevent: operator.evidence\ndata:{{"n":{eid}}}\n\n'.encode()

    with patch.object(hub, "subscribe", sub_all):
        stream = client.get("/v1/operator/events/stream")
        print(f"HTTP {stream.status_code} content-type={stream.headers.get('content-type')}")
        print(stream.text)
        if "id: 1" not in stream.text or "id: 2" not in stream.text:
            _fail("missing backlog events")
    print("captured last-event-id=2")
    return 2


def _step_sse_resume(client: TestClient, hub, org_id: str, last_id: int) -> None:
    print("\n# 5) Publish event 3, reconnect with Last-Event-ID (no duplicate of 1–2)")
    from uuid import UUID

    eid3 = asyncio.run(hub.publish({"n": 3}, org_id=UUID(org_id)))
    print(f"publish n=3 → event_id={eid3}")

    async def sub_resume(oid, last_event_id=None):
        if last_event_id != last_id:
            _fail(f"expected Last-Event-ID {last_id}, got {last_event_id}")
        yield b'id: 3\nevent: operator.evidence\ndata:{"n":3}\n\n'

    with patch.object(hub, "subscribe", sub_resume):
        stream = client.get(
            "/v1/operator/events/stream",
            headers={"Last-Event-ID": str(last_id)},
        )
        print(f"HTTP {stream.status_code} Last-Event-ID={last_id}")
        print(stream.text)
        if "id: 3" not in stream.text:
            _fail("missing resumed event")
        if "id: 1" in stream.text or "id: 2" in stream.text:
            _fail("duplicate old events on resume")
    print(f"resume OK — visible id 3 only (> {last_id})")


def _step_hub_resume(hub, org_id: str) -> None:
    print("\n# 5b) Hub Last-Event-ID filter (real ring buffer, org-scoped)")
    from uuid import UUID

    seen: list[int] = []
    oid = UUID(org_id)

    async def collect() -> None:
        agen = hub.subscribe(oid, 2)
        try:
            async for chunk in agen:
                if chunk.startswith(b"id:"):
                    seen.append(int(chunk.split(b"\n")[0].split(b":")[1].strip()))
                    break
        finally:
            await agen.aclose()

    asyncio.run(collect())
    print(f"hub resume after 2 → ids {seen}")
    if seen != [3]:
        _fail(f"hub resume ids {seen}")


def _step_drain(app, client: TestClient) -> None:
    print("\n# 6) Graceful drain — begin_drain then new SSE rejected")
    app.state.api.drain.begin_drain()
    drained = client.get("/v1/operator/events/stream")
    print(f"HTTP {drained.status_code} X-IBEX-Drain={drained.headers.get('X-IBEX-Drain')}")
    print(drained.json())
    if drained.status_code != 503:
        _fail("drain did not reject SSE")


def _step_rollback(client: TestClient, settings: Settings) -> None:
    print("\n=== ROLLBACK TRANSCRIPT (kill switch) ===")
    print("# Disable operator feature (docs origin unaffected — separate Pages project)")
    settings.operator_feature_enabled = False
    off = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_smoke"})
    print(f"login with kill-switch → HTTP {off.status_code} {off.json()}")
    if off.status_code != 503:
        _fail("kill switch did not 503")

    print("# Re-enable; unauthenticated SSE rejected")
    settings.operator_feature_enabled = True
    client.cookies.clear()
    unauth = client.get("/v1/operator/events/stream")
    print(f"SSE without session → HTTP {unauth.status_code} {unauth.json()}")
    if unauth.status_code not in (401, 403):
        _fail("unauth SSE not rejected")
    print("# Docs origin independence: web-deploy.yml / ibex-harness-docs untouched by")
    print("# IBEX_OPERATOR_FEATURE_ENABLED (operator-only kill switch on services/api).")


def main() -> None:
    print("=== 4.P.0 SMOKE TRANSCRIPT (login → API → SSE → resume → drain) ===")
    print(
        "$ cd services/api && uv run python "
        "../../web/engineering/research/operator-platform/4p0-smoke-transcript.py"
    )
    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        allowed_origins="http://localhost:3100",
        jwt_hmac_secret=_HMAC,
        dashboard_csrf_secret=_CSRF,
        cookie_secure=False,
        cookie_samesite="lax",
        operator_feature_enabled=True,
    )
    org = uuid4()
    validator = StaticTokenValidator(
        {"ibex_pat_smoke": ValidateResult(org_id=org, permissions=1, user_id="smoke-user")}
    )
    with (
        patch("app.main.create_engine", return_value=_engine()),
        patch("app.main.create_session_factory", return_value=MagicMock()),
        patch("authclient.revoke.GRPCTokenRevoker", return_value=MagicMock(aclose=AsyncMock())),
        patch("authclient.tokens.GRPCTokenManager", return_value=MagicMock(aclose=AsyncMock())),
        patch(
            "authclient.provider_credentials.GRPCProviderCredentialManager",
            return_value=MagicMock(aclose=AsyncMock()),
        ),
    ):
        app = create_app(settings=settings, validator=validator)
        with TestClient(app) as client:
            csrf, org_id = _step_login(client)
            _step_me(client)
            hub = app.state.operator_sse_hub
            _step_publish(hub, org_id)
            last_id = _step_sse_connect(client, hub)
            _step_sse_resume(client, hub, org_id, last_id)
            _step_hub_resume(hub, org_id)
            _step_drain(app, client)
            _step_rollback(client, settings)
            print("\nSMOKE+ROLLBACK OK")
            _ = csrf  # CSRF retained for transcript realism; mutations use hub helper


if __name__ == "__main__":
    main()
