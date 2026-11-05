"""Principal verification and selector binding tests (ADR-0096)."""

from __future__ import annotations

import pytest
from server_test_support import (
    AGENT,
    ORG,
    agent_id_text,
    org_id_text,
    principal_class,
    principal_message,
)

from app.principal import (
    AUTHORITY_AUTH_SERVICE,
    MAX_PRINCIPAL_SKEW_SECONDS,
    PrincipalError,
    PrincipalInvalid,
    PrincipalMismatch,
    PrincipalMissing,
    VerifiedPrincipal,
    bind_selectors,
    verify_principal,
)


@pytest.fixture
def pb2():
    from ibex.context.v1 import context_pb2

    return context_pb2


def _now() -> float:
    return 1_700_000_000.0


def _request(
    pb2,  # type: ignore[no-untyped-def]
    *,
    org_id: str | None = None,
    agent_id: str | None = None,
    principal: object | None = None,
):
    return pb2.AssembleContextRequest(
        org_id=org_id if org_id is not None else org_id_text(),
        agent_id=agent_id if agent_id is not None else agent_id_text(),
        model="gpt-4o-mini",
        principal_context=principal
        if principal is not None
        else principal_message(issued_at=_now()),
    )


def test_verify_principal_returns_canonical_identity(pb2) -> None:
    verified = verify_principal(_request(pb2), now=_now())
    assert isinstance(verified, VerifiedPrincipal)
    assert verified.org_id == ORG
    assert verified.agent_id == AGENT


def test_verify_principal_carries_correlation_ids(pb2) -> None:
    principal = principal_message(
        issued_at=_now(),
        request_id="req-1",
        trace_id="a" * 32,
    )
    verified = verify_principal(_request(pb2, principal=principal), now=_now())
    assert verified.request_id == "req-1"
    assert verified.trace_id == "a" * 32


def test_principal_authority_constant_matches_the_wire_contract() -> None:
    assert AUTHORITY_AUTH_SERVICE == "AuthService"


def test_verify_principal_requires_principal_context(pb2) -> None:
    request = pb2.AssembleContextRequest(
        org_id=org_id_text(),
        agent_id=agent_id_text(),
        model="gpt-4o-mini",
    )
    with pytest.raises(PrincipalMissing) as exc_info:
        verify_principal(request, now=_now())
    assert exc_info.value.reason == "missing"


def test_verify_principal_rejects_an_empty_principal(pb2) -> None:
    """An explicitly set but empty message is present-and-malformed."""
    request = pb2.AssembleContextRequest()
    request.principal_context.CopyFrom(principal_class()())
    with pytest.raises(PrincipalInvalid):
        verify_principal(request, now=_now())


@pytest.mark.parametrize("authority", ["", "AuthService ", "authservice", "Proxy"])
def test_verify_principal_rejects_other_authorities(pb2, authority: str) -> None:
    principal = principal_message(issued_at=_now(), authority=authority)
    with pytest.raises(PrincipalInvalid, match="authority"):
        verify_principal(_request(pb2, principal=principal), now=_now())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("org_id", ""),
        ("org_id", "NOT-A-UUID"),
        ("org_id", "0000000000000000000000000000b1"),
        ("agent_id", "{" + "0" * 35 + "}"),
        ("agent_id", "00000000-0000-0000-0000-0000000000B1"),
        ("agent_id", "urn:uuid:00000000-0000-0000-0000-0000000000b1"),
    ],
)
def test_verify_principal_requires_canonical_uuids(pb2, field: str, value: str) -> None:
    principal = principal_message(issued_at=_now())
    setattr(principal, field, value)
    with pytest.raises(PrincipalInvalid):
        verify_principal(_request(pb2, principal=principal), now=_now())


def test_principal_id_is_a_bounded_string_not_a_uuid(pb2) -> None:
    principal = principal_message(issued_at=_now(), principal_id="user:42/token-abc")
    verified = verify_principal(_request(pb2, principal=principal), now=_now())
    assert verified.org_id == ORG


@pytest.mark.parametrize(
    "principal_id",
    ["", " padded ", "x" * 257],
)
def test_verify_principal_rejects_unbounded_principal_ids(pb2, principal_id: str) -> None:
    principal = principal_message(issued_at=_now(), principal_id=principal_id)
    with pytest.raises(PrincipalInvalid, match="principal_id"):
        verify_principal(_request(pb2, principal=principal), now=_now())


def test_verify_principal_requires_issued_at(pb2) -> None:
    principal = principal_class()(
        org_id=org_id_text(),
        agent_id=agent_id_text(),
        principal_id="caller",
        authority="AuthService",
    )
    with pytest.raises(PrincipalInvalid, match="issued_at"):
        verify_principal(_request(pb2, principal=principal), now=_now())


@pytest.mark.parametrize("skew", [0.0, 29.0, -29.0, 30.0, -30.0])
def test_verify_principal_accepts_issued_at_within_the_skew_window(
    pb2,
    skew: float,
) -> None:
    principal = principal_message(issued_at=_now() + skew)
    assert verify_principal(_request(pb2, principal=principal), now=_now())


@pytest.mark.parametrize("skew", [31.0, -31.0, 600.0, -600.0])
def test_verify_principal_rejects_stale_or_future_issued_at(pb2, skew: float) -> None:
    principal = principal_message(issued_at=_now() + skew)
    with pytest.raises(PrincipalInvalid, match="issued_at"):
        verify_principal(_request(pb2, principal=principal), now=_now())


def test_verify_principal_accepts_absent_expires_at(pb2) -> None:
    principal = principal_message(issued_at=_now())
    assert not principal.HasField("expires_at")
    assert verify_principal(_request(pb2, principal=principal), now=_now())


@pytest.mark.parametrize("expires_in", [600.0, 31.0, 1.0])
def test_verify_principal_accepts_unexpired_expires_at(pb2, expires_in: float) -> None:
    principal = principal_message(issued_at=_now(), expires_at=_now() + expires_in)
    assert verify_principal(_request(pb2, principal=principal), now=_now())


@pytest.mark.parametrize("expires_in", [-31.0, -600.0])
def test_verify_principal_rejects_a_stale_expires_at(pb2, expires_in: float) -> None:
    principal = principal_message(issued_at=_now(), expires_at=_now() + expires_in)
    with pytest.raises(PrincipalInvalid, match="expired"):
        verify_principal(_request(pb2, principal=principal), now=_now())


def test_verify_principal_tolerates_small_expiry_skew(pb2) -> None:
    principal = principal_message(issued_at=_now(), expires_at=_now() - 10.0)
    assert verify_principal(_request(pb2, principal=principal), now=_now())


def test_verify_principal_defaults_to_wall_clock(pb2) -> None:
    verified = verify_principal(_request(pb2, principal=principal_message()))
    assert verified.org_id == ORG


def test_verify_principal_rejects_an_oversized_request_id(pb2) -> None:
    principal = principal_message(issued_at=_now(), request_id="r" * 129)
    with pytest.raises(PrincipalInvalid, match="correlation"):
        verify_principal(_request(pb2, principal=principal), now=_now())


def test_verify_principal_ignores_permissions_and_token_id(pb2) -> None:
    principal = principal_message(issued_at=_now())
    principal.permissions = 0
    principal.token_id = "not-a-uuid"
    principal.source = ""
    assert verify_principal(_request(pb2, principal=principal), now=_now())


def _verified() -> VerifiedPrincipal:
    return VerifiedPrincipal(org_id=ORG, agent_id=AGENT)


def test_bind_selectors_accepts_matching_selectors(pb2) -> None:
    bind_selectors(_request(pb2), _verified())


@pytest.mark.parametrize(
    "selectors",
    [
        (org_id_text(org_id="00000000-0000-0000-0000-0000000000b1"), agent_id_text()),
        (org_id_text(), agent_id_text(agent_id="00000000-0000-0000-0000-0000000000b3")),
        ("", agent_id_text()),
        (org_id_text(), ""),
        ("not-a-uuid", agent_id_text()),
        (org_id_text().upper(), agent_id_text()),
    ],
)
def test_bind_selectors_rejects_any_non_identical_selector(pb2, selectors) -> None:
    request = _request(pb2, org_id=selectors[0], agent_id=selectors[1])
    with pytest.raises(PrincipalMismatch) as exc_info:
        bind_selectors(request, _verified())
    assert exc_info.value.reason == "mismatch"


def test_principal_error_hierarchy_is_typed() -> None:
    assert issubclass(PrincipalInvalid, PrincipalError)
    assert issubclass(PrincipalMismatch, PrincipalError)
    assert issubclass(PrincipalMissing, PrincipalError)
    assert PrincipalMissing().reason == "missing"
    assert PrincipalInvalid().reason == "invalid"
    assert PrincipalMismatch().reason == "mismatch"


def test_skew_constant_matches_the_contract() -> None:
    assert MAX_PRINCIPAL_SKEW_SECONDS == 30.0


class _PlainPrincipal:
    """Duck-typed principal (no protobuf): exercises the non-proto fallbacks."""

    def __init__(self, **fields: object) -> None:
        for key, value in fields.items():
            setattr(self, key, value)


class _PlainRequest:
    def __init__(self, principal: object) -> None:
        self.principal_context = principal


def _plain_principal(**overrides: object) -> _PlainPrincipal:
    fields: dict[str, object] = {
        "org_id": org_id_text(),
        "agent_id": agent_id_text(),
        "principal_id": "caller",
        "authority": "AuthService",
        "issued_at": _now(),
    }
    fields.update(overrides)
    return _PlainPrincipal(**fields)


def test_verify_principal_accepts_a_duck_typed_principal() -> None:
    """Absent ``HasField``/``expires_at`` is treated as "present but optional"."""
    verified = verify_principal(_PlainRequest(_plain_principal()), now=_now())
    assert verified.org_id == ORG
    assert verified.agent_id == AGENT


def test_verify_principal_accepts_numeric_timestamps_on_duck_typed_input() -> None:
    principal = _plain_principal(expires_at=_now() + 60.0)
    assert verify_principal(_PlainRequest(principal), now=_now())


def test_verify_principal_rejects_a_non_timestamp_issued_at() -> None:
    principal = _plain_principal(issued_at="soon")
    with pytest.raises(PrincipalInvalid, match="proto timestamp"):
        verify_principal(_PlainRequest(principal), now=_now())


def test_verify_principal_rejects_a_non_string_field() -> None:
    principal = _plain_principal(authority=123)
    with pytest.raises(PrincipalInvalid, match="must be a string"):
        verify_principal(_PlainRequest(principal), now=_now())


def test_verify_principal_treats_has_field_errors_as_present() -> None:
    class _RaisingRequest(_PlainRequest):
        def HasField(self, name: str) -> bool:
            raise ValueError(f"{name} is not a message field")

    verified = verify_principal(_RaisingRequest(_plain_principal()), now=_now())
    assert verified.org_id == ORG
