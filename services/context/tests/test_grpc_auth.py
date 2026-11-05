"""Caller-token guard tests (ADR-0096)."""

from __future__ import annotations

import logging
from collections import namedtuple

import grpc
import pytest
from pydantic import SecretStr

from app import grpc_auth
from app.grpc_auth import (
    REASON_DUPLICATE,
    REASON_INVALID,
    REASON_MISMATCH,
    REASON_MISSING,
    SERVICE_TOKEN_METADATA_KEY,
    UNAUTHENTICATED_DETAILS,
    guard_handler,
    require_service_token,
    secret_value,
    tokens_match,
    validate_service_token,
)

TOKEN = "context-test-service-token-0123456789abcdef"
OTHER = "context-test-service-token-fedcba9876543210"
Metadatum = namedtuple("Metadatum", ["key", "value"])


class _Ctx:
    def __init__(self, metadata: object = ()) -> None:
        self._metadata = metadata
        self.aborts: list[tuple[object, str]] = []

    def invocation_metadata(self):  # type: ignore[no-untyped-def]
        if isinstance(self._metadata, Exception):
            raise self._metadata
        return self._metadata

    async def abort(self, code, details):  # type: ignore[no-untyped-def]
        self.aborts.append((code, details))
        raise grpc.aio.AioRpcError(code, details=details)


async def _rejection(ctx: object) -> grpc.aio.AioRpcError:
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        await require_service_token(ctx, TOKEN, method="AssembleContext")  # type: ignore[arg-type]
    return exc_info.value


async def _accepted(metadata: object) -> None:
    """Assert the guard accepts invocation metadata and records no abort."""
    ctx = _Ctx(metadata)
    await require_service_token(ctx, TOKEN, method="AssembleContext")  # type: ignore[arg-type]
    assert ctx.aborts == []


async def _rejected_context(
    ctx: object,
    caplog: pytest.LogCaptureFixture,
    *,
    reason: str | None = None,
) -> grpc.aio.AioRpcError:
    """Assert an UNAUTHENTICATED rejection, optionally pinning the log reason."""
    with caplog.at_level(logging.WARNING, logger="app.grpc_auth"):
        err = await _rejection(ctx)
    assert err.code() == grpc.StatusCode.UNAUTHENTICATED
    if reason is not None:
        assert f"reason={reason}" in caplog.text
    return err


async def _rejected(
    metadata: object,
    caplog: pytest.LogCaptureFixture,
    *,
    reason: str | None = None,
) -> grpc.aio.AioRpcError:
    """Assert an UNAUTHENTICATED rejection for raw invocation metadata."""
    return await _rejected_context(_Ctx(metadata), caplog, reason=reason)


def _recorder() -> tuple[grpc_auth.Handler, list[object]]:
    """A handler stand-in that records the requests it is called with."""
    calls: list[object] = []

    async def _handler(request: object, _context: object) -> object:
        calls.append(request)
        return "ok"

    return _handler, calls


def test_validate_service_token_accepts_a_configured_token() -> None:
    assert validate_service_token(TOKEN) == TOKEN
    assert validate_service_token(SecretStr(TOKEN)) == TOKEN


@pytest.mark.parametrize(
    "value",
    ["", None, "short", "has space " * 8, "a" * 513, "unicode-é" * 8],
)
def test_validate_service_token_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValueError, match="IBEX_CONTEXT_GRPC_SERVICE_TOKEN"):
        validate_service_token(value)  # type: ignore[arg-type]


def test_validate_service_token_never_echoes_the_value() -> None:
    with pytest.raises(ValueError) as exc_info:
        validate_service_token("secret-but-too-short")
    assert "secret-but-too-short" not in str(exc_info.value)


@pytest.mark.parametrize("value", ["", None, SecretStr("")])
def test_secret_value_handles_empty_inputs(value: object) -> None:
    assert secret_value(value) == ""  # type: ignore[arg-type]


def test_secret_value_unwraps_secret_str() -> None:
    assert secret_value(SecretStr(TOKEN)) == TOKEN
    assert secret_value(TOKEN) == TOKEN


def test_tokens_match_is_exact() -> None:
    assert tokens_match(TOKEN, TOKEN)
    assert not tokens_match(OTHER, TOKEN)
    assert not tokens_match(TOKEN[:31], TOKEN)
    assert not tokens_match(None, TOKEN)
    assert not tokens_match(TOKEN, "")


def test_tokens_match_returns_false_on_type_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args, **_kwargs):
        raise TypeError("unsupported operand")

    monkeypatch.setattr(grpc_auth.hmac, "compare_digest", _boom)
    assert tokens_match(TOKEN, TOKEN) is False


@pytest.mark.asyncio
async def test_require_service_token_accepts_single_matching_entry() -> None:
    await _accepted(((SERVICE_TOKEN_METADATA_KEY, TOKEN),))


@pytest.mark.asyncio
async def test_require_service_token_accepts_metadatum_objects() -> None:
    await _accepted([Metadatum(SERVICE_TOKEN_METADATA_KEY, TOKEN)])


@pytest.mark.asyncio
async def test_require_service_token_normalizes_keys_and_bytes_values() -> None:
    await _accepted([(SERVICE_TOKEN_METADATA_KEY.upper().encode(), TOKEN.encode())])


@pytest.mark.asyncio
async def test_require_service_token_rejects_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    err = await _rejected((), caplog, reason=REASON_MISSING)
    assert err.details() == UNAUTHENTICATED_DETAILS


@pytest.mark.asyncio
async def test_require_service_token_rejects_duplicate(
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _rejected(
        (
            (SERVICE_TOKEN_METADATA_KEY, TOKEN),
            (SERVICE_TOKEN_METADATA_KEY, TOKEN),
        ),
        caplog,
        reason=REASON_DUPLICATE,
    )


@pytest.mark.asyncio
async def test_require_service_token_rejects_mismatch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _rejected(((SERVICE_TOKEN_METADATA_KEY, OTHER),), caplog, reason=REASON_MISMATCH)
    assert TOKEN not in caplog.text
    assert OTHER not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [42, None, b"short", TOKEN.encode()[:10]],
)
async def test_require_service_token_rejects_invalid_value(
    value: object,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _rejected(((SERVICE_TOKEN_METADATA_KEY, value),), caplog, reason=REASON_INVALID)


@pytest.mark.asyncio
async def test_require_service_token_rejects_unreadable_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _rejected(RuntimeError("metadata unavailable"), caplog)


@pytest.mark.asyncio
async def test_require_service_token_rejects_malformed_entry(
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _rejected([object()], caplog)


@pytest.mark.asyncio
async def test_require_service_token_rejects_lone_surrogates(
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _rejected(((SERVICE_TOKEN_METADATA_KEY, "\ud800" * 20),), caplog, reason=REASON_INVALID)


@pytest.mark.asyncio
async def test_require_service_token_rejects_undecodable_bytes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _rejected(((SERVICE_TOKEN_METADATA_KEY, b"\xff" * 40),), caplog, reason=REASON_INVALID)


@pytest.mark.asyncio
@pytest.mark.parametrize("key", [b"\xff" * 4, 42])
async def test_require_service_token_ignores_unusable_keys(
    key: object,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _rejected(((key, TOKEN),), caplog, reason=REASON_MISSING)


@pytest.mark.asyncio
async def test_require_service_token_rejects_context_without_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _Bare:
        async def abort(self, code, details):  # type: ignore[no-untyped-def]
            raise grpc.aio.AioRpcError(code, details=details)

    await _rejected_context(_Bare(), caplog)


@pytest.mark.asyncio
async def test_guard_handler_runs_the_handler_when_authenticated() -> None:
    handler, calls = _recorder()
    guarded = guard_handler(handler, TOKEN, method="AssembleContext")
    ctx = _Ctx(((SERVICE_TOKEN_METADATA_KEY, TOKEN),))
    assert await guarded("req", ctx) == "ok"  # type: ignore[arg-type]
    assert calls == ["req"]


@pytest.mark.asyncio
async def test_guard_handler_blocks_the_handler_when_unauthenticated() -> None:
    handler, calls = _recorder()
    guarded = guard_handler(handler, SecretStr(TOKEN))
    with pytest.raises(grpc.aio.AioRpcError):
        await guarded("req", _Ctx(()))  # type: ignore[arg-type]
    assert calls == []


def test_guard_handler_rejects_an_invalid_configured_token() -> None:
    handler, _calls = _recorder()

    with pytest.raises(ValueError, match="IBEX_CONTEXT_GRPC_SERVICE_TOKEN"):
        guard_handler(handler, "")
