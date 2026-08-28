"""Targeted unit tests for patch coverage gaps on new m3.C.5 code."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import grpc
import pytest
from authclient import AuthCodecError, ValidateTokenWire
from authclient.codec import (
    _WIRE_LEN,
    _WIRE_VARINT,
    MAX_STRING_BYTES,
    _bounded_string,
    _skip_unknown,
    decode_validate_token_response,
    encode_varint,
)
from authclient.target import _host_of
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.auth.client import TokenValidator
from app.auth.errors import AuthUnavailableError
from app.config import Settings
from app.exceptions import EmbeddingServiceError
from app.main import MemoryAppState, create_app
from app.pipeline.context import WriteContext
from app.write.after_commit import AfterCommitHandler
from app.write.embed_context import get_write_org_id
from app.write.errors import is_active_content_hash_violation
from app.write.factory import build_write_pipeline
from app.write.models import CreateMemoryCommand, WriteOutcome, WriteOutcomeKind
from app.write.orchestrator import MemoryWriteOrchestrator
from app.write.persist import _aware, _aware_opt
from tests.unit.auth_test_support import encode_validate_token_wire, grpc_validator, rpc_error
from tests.unit.memory_test_support import sample_memory_row


def test_proto_wire_skips_unknown_len_field_and_token_id() -> None:
    org_id = uuid4()
    org_bytes = str(org_id).encode()
    token_id = b"tok-abc"
    # field 6 (wire len) ignored + field 5 token_id + field 1 org_id
    unknown = bytes([0x32]) + encode_varint(3) + b"zzz"
    token_field = bytes([0x2A]) + encode_varint(len(token_id)) + token_id
    org_field = bytes([0x0A]) + encode_varint(len(org_bytes)) + org_bytes
    payload = unknown + org_field + token_field
    wire = decode_validate_token_response(payload)
    assert wire.org_id == org_id
    assert wire.token_id == "tok-abc"


def test_proto_wire_skip_varint_and_truncated_fixed() -> None:
    org_id = uuid4()
    org_bytes = str(org_id).encode()
    org_field = bytes([0x0A]) + encode_varint(len(org_bytes)) + org_bytes
    # unknown varint field 9 (wire 0)
    unknown_varint = bytes([0x48, 0x01])
    # truncated fixed64 (wire 1) - only 4 bytes
    truncated_fixed = bytes([0x09]) + b"\x00" * 4
    with pytest.raises(AuthCodecError, match="truncated fixed64"):
        decode_validate_token_response(org_field + unknown_varint + truncated_fixed)


def test_proto_wire_unsupported_wire_type() -> None:
    with pytest.raises(AuthCodecError, match="unsupported wire type"):
        decode_validate_token_response(bytes([0x07]))


def test_proto_wire_user_id_field() -> None:
    org_id = uuid4()
    org_bytes = str(org_id).encode()
    uid = b"user-42"
    payload = (
        bytes([0x0A]) + encode_varint(len(org_bytes)) + org_bytes + bytes([0x22])
        + encode_varint(len(uid))
        + uid
    )
    wire = decode_validate_token_response(payload)
    assert wire.user_id == "user-42"


def test_host_of_without_port() -> None:
    assert _host_of("memory-service") == "memory-service"


@pytest.mark.asyncio
async def test_grpc_validator_ready_success() -> None:
    org_id = uuid4()
    wire = ValidateTokenWire(org_id=org_id, permissions=1)
    with grpc_validator(return_value=encode_validate_token_wire(wire)) as validator:
        assert await validator.ready() is True
        await validator.aclose()


class _CallsSuperValidator(TokenValidator):
    async def validate(self, access_token: str):
        return await TokenValidator.validate(self, access_token)

    async def ready(self) -> bool:
        return await TokenValidator.ready(self)

    async def aclose(self) -> None:
        await TokenValidator.aclose(self)


@pytest.mark.asyncio
async def test_token_validator_validate_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        await _CallsSuperValidator().validate("x")


@pytest.mark.asyncio
async def test_token_validator_ready_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        await _CallsSuperValidator().ready()


@pytest.mark.asyncio
async def test_token_validator_aclose_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        await _CallsSuperValidator().aclose()


def test_get_write_org_id_missing_raises() -> None:
    with pytest.raises(RuntimeError, match="not set"):
        get_write_org_id()


def test_is_active_content_hash_violation_no_orig() -> None:
    exc = IntegrityError("stmt", {}, Exception("x"))
    exc.orig = None  # type: ignore[assignment]
    assert is_active_content_hash_violation(exc) is False


def test_aware_helpers() -> None:
    naive = datetime(2026, 1, 1, 12, 0, 0)  # noqa: DTZ001 — intentional naive input
    assert _aware(naive).tzinfo == UTC
    assert _aware_opt(None) is None
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert _aware_opt(aware).tzinfo == UTC


@pytest.mark.asyncio
async def test_after_commit_skips_non_created() -> None:
    cache = AsyncMock()
    handler = AfterCommitHandler(cache=cache, store=None)
    row = sample_memory_row()
    await handler(WriteOutcome(kind=WriteOutcomeKind.QUARANTINED, memory=row))
    cache.write_created.assert_not_awaited()


@pytest.mark.asyncio
async def test_after_commit_writes_cache() -> None:
    cache = AsyncMock()
    cache.write_created = AsyncMock()
    handler = AfterCommitHandler(cache=cache, store=None)
    row = sample_memory_row()
    await handler(WriteOutcome(kind=WriteOutcomeKind.CREATED, memory=row))
    cache.write_created.assert_awaited_once()


@pytest.mark.asyncio
async def test_factory_inner_callbacks_invoked() -> None:
    settings = Settings(embedding_api_token="tok")
    session_factory = MagicMock()
    store = MagicMock()
    pii = MagicMock()
    embed = AsyncMock()
    org_id = uuid4()
    agent_id = uuid4()
    memory_id = uuid4()

    with (
        patch(
            "app.write.factory.find_active_by_content_hash",
            AsyncMock(return_value=memory_id),
        ) as lookup_mock,
        patch(
            "app.write.factory.increment_retrieval_count",
            AsyncMock(return_value=2),
        ) as bump_mock,
        patch(
            "app.write.factory.load_candidate_memories",
            AsyncMock(return_value=[]),
        ) as load_mock,
    ):
        pipeline = build_write_pipeline(
            settings,
            session_factory=session_factory,
            store=store,
            pii=pii,
            embed=embed,
        )
        exact_stage = pipeline._stages[2]
        ctx = WriteContext(
            org_id=org_id,
            agent_id=agent_id,
            content="duplicate text here",
            content_hash="abc",
        )
        await exact_stage.process(ctx)
        lookup_mock.assert_awaited()
        bump_mock.assert_awaited()

        conflict_stage = pipeline._stages[5]
        ctx.near_duplicate_candidates = [uuid4()]
        await conflict_stage.process(ctx)
        load_mock.assert_awaited()


@pytest.mark.asyncio
async def test_orchestrator_reraises_non_embedding_errors() -> None:
    class _Boom:
        async def run(self, _ctx: WriteContext) -> WriteContext:
            raise RuntimeError("boom")

    orch = MemoryWriteOrchestrator(_Boom(), MagicMock())
    with pytest.raises(RuntimeError, match="boom"):
        await orch.create(
            CreateMemoryCommand(org_id=uuid4(), agent_id=uuid4(), content="x")
        )


@pytest.mark.asyncio
async def test_orchestrator_quarantine_calls_after_commit() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    after_commit = AsyncMock()

    class _Pipe:
        async def run(self, ctx: WriteContext) -> WriteContext:
            ctx.status = "quarantined"
            return ctx

    mock_session = MagicMock()
    mock_begin = MagicMock()
    mock_begin.__aenter__ = AsyncMock(return_value=mock_session)
    mock_begin.__aexit__ = AsyncMock(return_value=None)
    mock_session.begin = MagicMock(return_value=mock_begin)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    orch = MemoryWriteOrchestrator(_Pipe(), MagicMock(return_value=mock_cm), after_commit=after_commit)
    fake_row = sample_memory_row(
        org_id=org_id,
        agent_id=agent_id,
        content="quarantine",
        status="quarantined",
        pii_detected=True,
    )
    with patch("app.write.orchestrator.insert_memory_session", AsyncMock(return_value=fake_row)):
        await orch.create(
            CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content="quarantine")
        )
    after_commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_orchestrator_active_missing_content_hash() -> None:
    class _Pipe:
        async def run(self, ctx: WriteContext) -> WriteContext:
            ctx.status = "active"
            ctx.content_hash = None
            return ctx

    orch = MemoryWriteOrchestrator(_Pipe(), MagicMock())
    with pytest.raises(RuntimeError, match="content_hash required"):
        await orch.create(
            CreateMemoryCommand(org_id=uuid4(), agent_id=uuid4(), content="active")
        )


def test_deps_success_paths() -> None:
    from unittest.mock import MagicMock

    from app.deps import get_session_factory, get_write_orchestrator

    state = MemoryAppState()
    sentinel_factory = object()
    sentinel_orch = object()
    state.session_factory = sentinel_factory  # type: ignore[assignment]
    state.write_orchestrator = sentinel_orch  # type: ignore[assignment]
    request = MagicMock()
    request.app.state.memory = state
    assert get_session_factory(request) is sentinel_factory
    assert get_write_orchestrator(request) is sentinel_orch


def test_main_auth_not_ready() -> None:
    from fastapi.testclient import TestClient

    from app.auth.client import StaticTokenValidator

    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        embedding_api_token="tok",
    )
    validator = StaticTokenValidator({}, available=False)
    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()

    with (
        patch("app.main.create_engine", return_value=mock_engine),
        patch("app.main.create_session_factory", return_value=MagicMock()),
        patch("app.main.PgVectorStore", return_value=MagicMock()),
        patch("app.main.PiiService", return_value=MagicMock()),
        patch("app.main.build_write_orchestrator", return_value=MagicMock()),
        patch("app.main._postgres_ready", AsyncMock(return_value=True)),
    ):
        app = create_app(settings=settings, validator=validator)
        with TestClient(app) as client:
            assert app.state.memory.ready is False
            assert app.state.memory.ready_error == "auth gRPC not reachable"
            assert client.get("/ready").status_code == 503


def test_http_error_for_write_reraises_unknown() -> None:
    from app.routers.memory_write_support import http_error_for_write

    with pytest.raises(ValueError, match="nope"):
        http_error_for_write(ValueError("nope"))


def test_http_error_for_write_maps_embedding() -> None:
    from app.routers.memory_write_support import http_error_for_write

    exc = http_error_for_write(EmbeddingServiceError("down"))
    assert exc.status_code == 503
    assert exc.detail["code"] == "EMBEDDING_FAILED"


@pytest.mark.asyncio
async def test_begin_idempotency_conflict_and_in_progress() -> None:
    from app.idempotency.redis_store import ClaimKind, ClaimOutcome, pending_record
    from app.routers.memory_write_support import begin_idempotency

    store = AsyncMock()
    store.claim = AsyncMock(
        return_value=ClaimOutcome(kind=ClaimKind.CONFLICT, record=pending_record("fp"))
    )
    with pytest.raises(HTTPException) as exc:
        await begin_idempotency(
            store=store,
            org_id=uuid4(),
            idempotency_key="k",
            fingerprint="fp",
        )
    assert exc.value.status_code == 409

    store.claim = AsyncMock(
        return_value=ClaimOutcome(kind=ClaimKind.IN_PROGRESS, record=pending_record("fp"))
    )
    with pytest.raises(HTTPException) as exc:
        await begin_idempotency(
            store=store,
            org_id=uuid4(),
            idempotency_key="k",
            fingerprint="fp",
        )
    assert exc.value.detail["code"] == "IDEMPOTENCY_IN_PROGRESS"


@pytest.mark.asyncio
async def test_orchestrator_after_commit_failure_does_not_propagate() -> None:
    after_commit = AsyncMock(side_effect=RuntimeError("cache down"))

    class _Pipe:
        async def run(self, ctx: WriteContext) -> WriteContext:
            ctx.status = "active"
            ctx.content_hash = "abc"
            return ctx

    mock_session = MagicMock()
    mock_begin = MagicMock()
    mock_begin.__aenter__ = AsyncMock(return_value=mock_session)
    mock_begin.__aexit__ = AsyncMock(return_value=None)
    mock_session.begin = MagicMock(return_value=mock_begin)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    orch = MemoryWriteOrchestrator(
        _Pipe(),
        MagicMock(return_value=mock_cm),
        after_commit=after_commit,
    )
    fake_row = sample_memory_row(content="x")
    with patch("app.write.orchestrator.insert_memory_session", AsyncMock(return_value=fake_row)):
        outcome = await orch.create(
            CreateMemoryCommand(org_id=uuid4(), agent_id=uuid4(), content="x")
        )
    assert outcome.kind == WriteOutcomeKind.CREATED
    after_commit.assert_awaited_once()


def test_map_rpc_error_unknown_code() -> None:
    from app.auth.client import _map_rpc_error

    mapped = _map_rpc_error(rpc_error(grpc.StatusCode.UNAVAILABLE))
    assert isinstance(mapped, AuthUnavailableError)


def test_proto_wire_skip_len_delimited_unknown_field() -> None:
    org_id = uuid4()
    org_bytes = str(org_id).encode()
    # field 6 len-delimited (skipped via _read_bytes in _skip_unknown)
    skip = bytes([0x32]) + encode_varint(2) + b"xx"
    org_field = bytes([0x0A]) + encode_varint(len(org_bytes)) + org_bytes
    wire = decode_validate_token_response(skip + org_field)
    assert wire.org_id == org_id


def test_proto_wire_skip_unknown_helpers_directly() -> None:
    varint_buf = bytes([0x01])
    assert _skip_unknown(varint_buf, 0, _WIRE_VARINT) == 1
    len_buf = encode_varint(2) + b"ab"
    assert _skip_unknown(len_buf, 0, _WIRE_LEN) == 3


def test_proto_wire_bounded_string_limit() -> None:
    with pytest.raises(AuthCodecError, match="exceeds limit"):
        _bounded_string("x" * (MAX_STRING_BYTES + 1), "user_id")
