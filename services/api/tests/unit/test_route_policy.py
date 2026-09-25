from __future__ import annotations

from app.main import create_app
from app.route_policy import ROUTE_POLICY, mounted_route_keys, policy_keys


def test_route_policy_covers_every_mounted_route() -> None:
    app = create_app()
    assert policy_keys() == mounted_route_keys(app)


def test_route_policy_rows_declare_security_contract_fields() -> None:
    required = {
        "method",
        "path",
        "auth_source",
        "role",
        "permission",
        "organization_source",
        "anti_enumeration",
        "unavailable_result",
        "csrf_origin_required",
        "cache_control",
        "evidence",
    }
    assert ROUTE_POLICY
    for row in ROUTE_POLICY:
        assert required <= row.keys()
