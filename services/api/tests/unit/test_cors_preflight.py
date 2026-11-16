"""Browser preflight for the org-deletion step-up header.

A cross-origin ``DELETE`` that carries ``Authorization`` and ``X-IBEX-Step-Up``
sends an ``OPTIONS`` preflight naming both headers. If the API does not allow
the second one, the browser rejects the request before the route can ask for a
proof, so an owner on an allowed origin cannot delete the organization at all.
"""

from __future__ import annotations

import httpx

from tests.unit.org_user_test_support import ApiClientOpts, api_client

_ORIGIN = "http://localhost:3100"  # the default IBEX_ALLOWED_ORIGINS entry
_ORG_PATH = "/v1/organizations/00000000-0000-0000-0000-000000000000"


def _allowed_headers(resp: httpx.Response) -> set[str]:
    raw = resp.headers["access-control-allow-headers"]
    return {part.strip().lower() for part in raw.split(",")}


def test_preflight_allows_the_step_up_header_on_delete() -> None:
    with api_client(ApiClientOpts()) as (client, _res, _pub):
        resp = client.options(
            _ORG_PATH,
            headers={
                "Origin": _ORIGIN,
                "Access-Control-Request-Method": "DELETE",
                "Access-Control-Request-Headers": "authorization, x-ibex-step-up",
            },
        )

    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == _ORIGIN
    assert "DELETE" in resp.headers["access-control-allow-methods"]
    assert {"authorization", "x-ibex-step-up"} <= _allowed_headers(resp)


def test_preflight_still_refuses_an_unlisted_header() -> None:
    """The allowlist stays closed: only the headers the API serves are admitted."""
    with api_client(ApiClientOpts()) as (client, _res, _pub):
        resp = client.options(
            _ORG_PATH,
            headers={
                "Origin": _ORIGIN,
                "Access-Control-Request-Method": "DELETE",
                "Access-Control-Request-Headers": "authorization, x-not-a-real-header",
            },
        )

    assert resp.status_code == 400
