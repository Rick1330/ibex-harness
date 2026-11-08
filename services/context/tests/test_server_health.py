"""Standard gRPC health service over a real aio channel (readiness slice)."""

from __future__ import annotations

import asyncio

import grpc
import pytest
from grpc_health.v1 import health_pb2, health_pb2_grpc
from server_test_support import assembler as _assembler
from server_test_support import settings as _settings

from app.server import AssemblyRuntime, _shutdown_runtime, _start_listening


class _FakeMemory:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_health_check_reports_serving_over_a_real_channel() -> None:
    """The real server answers Health/Check without a caller token."""
    runtime = AssemblyRuntime(
        assembler=_assembler(),
        memory=_FakeMemory(),  # type: ignore[arg-type]
        redis_client=None,
    )
    loop = asyncio.get_running_loop()
    server, port, health_servicer = await _start_listening(runtime, _settings())
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    stub = health_pb2_grpc.HealthStub(channel)
    try:
        response = await stub.Check(
            health_pb2.HealthCheckRequest(service=""),
            timeout=5.0,
        )
        assert response.status == health_pb2.HealthCheckResponse.SERVING

        health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
        response = await stub.Check(
            health_pb2.HealthCheckRequest(service=""),
            timeout=5.0,
        )
        assert response.status == health_pb2.HealthCheckResponse.NOT_SERVING
    finally:
        await channel.close()
        await _shutdown_runtime(loop, server, runtime, health_servicer)

    assert runtime.memory.closed is True


@pytest.mark.asyncio
async def test_shutdown_marks_not_serving_before_stopping() -> None:
    order: list[str] = []

    class _FakeServer:
        async def stop(self, grace: float | None = None) -> None:
            del grace
            order.append("stop")

    class _FakeHealth:
        def set(self, service: str, status: object) -> None:
            del service, status
            order.append("not_serving")

    class _FakeRuntime:
        async def aclose(self) -> None:
            order.append("aclose")

    loop = asyncio.get_running_loop()
    await _shutdown_runtime(
        loop,
        _FakeServer(),  # type: ignore[arg-type]
        _FakeRuntime(),  # type: ignore[arg-type]
        _FakeHealth(),  # type: ignore[arg-type]
    )

    assert order == ["not_serving", "stop", "aclose"]
