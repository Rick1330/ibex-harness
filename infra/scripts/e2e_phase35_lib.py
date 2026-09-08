#!/usr/bin/env python3
"""Shared helpers for Phase 3.5 learning-loop e2e (kept small for CodeScene)."""

from __future__ import annotations

import json
import math
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

try:
    import grpc
    from ibex.context.v1 import context_pb2
except ImportError:  # pragma: no cover
    grpc = None  # type: ignore[assignment]
    context_pb2 = None  # type: ignore[assignment]


@dataclass(frozen=True)
class Env:
    proxy: str
    memory: str
    mcp: str
    context_addr: str
    auth_token: str
    org_a: str
    agent_a: str
    org_b: str
    agent_b: str
    token_b: str
    marker: str
    mcp_marker: str
    context_pid: int | None
    worker_log: str | None
    timeout_s: float
    interval_s: float


@dataclass(frozen=True)
class Tenant:
    """Auth identity for HTTP calls (cuts excess kwarg smells)."""

    token: str
    agent: str


def env_from_os() -> Env:
    pid_raw = os.environ.get("IBEX_E2E_P35_CONTEXT_PID", "").strip()
    return Env(
        proxy=os.environ.get("IBEX_PROXY_ADDR", "http://127.0.0.1:18080").rstrip("/"),
        memory=os.environ.get("IBEX_MEMORY_ADDR", "http://127.0.0.1:8005").rstrip("/"),
        mcp=os.environ.get("IBEX_MCP_ADDR", "http://127.0.0.1:18090").rstrip("/"),
        context_addr=os.environ.get("IBEX_CONTEXT_GRPC_ADDR", "127.0.0.1:9092"),
        auth_token=os.environ.get(
            "IBEX_DEV_TOKEN",
            "ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY",
        ),
        org_a=os.environ.get(
            "IBEX_DEV_ORG_ID", "00000000-0000-0000-0000-000000000001"
        ),
        agent_a=os.environ.get(
            "IBEX_DEV_AGENT_ID", "00000000-0000-0000-0000-000000000003"
        ),
        org_b=os.environ.get(
            "IBEX_E2E_P35_ORG_B", "00000000-0000-0000-0000-0000000000b1"
        ),
        agent_b=os.environ.get(
            "IBEX_E2E_P35_AGENT_B", "00000000-0000-0000-0000-0000000000b3"
        ),
        token_b=os.environ.get(
            "IBEX_E2E_P35_TOKEN_B",
            "ibex_pat_00000000-0000-0000-0000-0000000000b4_LOCALDEVELOPMENTONLY",
        ),
        marker=os.environ["IBEX_E2E_P35_MARKER"],
        mcp_marker=os.environ.get("IBEX_E2E_P35_MCP_MARKER", "mcp oak pine cedar maple"),
        context_pid=int(pid_raw) if pid_raw.isdigit() else None,
        worker_log=os.environ.get("IBEX_E2E_P35_WORKER_LOG") or None,
        timeout_s=float(os.environ.get("IBEX_E2E_P35_EVENTUALLY_TIMEOUT", "60")),
        interval_s=float(os.environ.get("IBEX_E2E_P35_EVENTUALLY_INTERVAL", "0.25")),
    )


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def pass_(msg: str) -> None:
    print(f"PASS: {msg}")


def eventually(
    assertion: Callable[[], None],
    *,
    timeout: float,
    interval: float,
    label: str,
) -> None:
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            assertion()
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(interval)
    fail(f"{label}: not satisfied within {timeout}s ({last!r})")


def org_a_tenant(env: Env) -> Tenant:
    return Tenant(token=env.auth_token, agent=env.agent_a)


def org_b_tenant(env: Env) -> Tenant:
    return Tenant(token=env.token_b, agent=env.agent_b)


def _auth_headers(tenant: Tenant) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tenant.token}",
        "Content-Type": "application/json",
        "X-IBEX-Agent-ID": tenant.agent,
    }


@dataclass(frozen=True)
class ChatOpts:
    tenant: Tenant | None = None
    session_id: str | None = None


def chat(
    client: httpx.Client,
    env: Env,
    content: str,
    opts: ChatOpts | None = None,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    flags = opts or ChatOpts()
    who = flags.tenant or org_a_tenant(env)
    headers = _auth_headers(who)
    if flags.session_id:
        headers["X-IBEX-Session-ID"] = flags.session_id
    body = {"model": "gpt-4o", "messages": [{"role": "user", "content": content}]}
    resp = client.post(f"{env.proxy}/v1/chat/completions", headers=headers, json=body)
    hdrs = {k.lower(): v for k, v in resp.headers.items()}
    try:
        payload = resp.json()
    except json.JSONDecodeError:
        payload = {"raw": resp.text[:500]}
    return resp.status_code, hdrs, payload


def require_chat_ok(code: int, label: str) -> None:
    if code in {429, 503}:
        raise AssertionError(f"{label}: transient HTTP {code}; will retry")
    if code != 200:
        raise AssertionError(f"{label} HTTP {code}")


def terminate(client: httpx.Client, env: Env, session_id: str) -> int:
    resp = client.post(
        f"{env.proxy}/v1/sessions/{session_id}/terminate",
        headers=_auth_headers(org_a_tenant(env)),
        json={"status": "completed"},
    )
    return resp.status_code


def memory_content(marker: str) -> str:
    return f"ibex phase three five learning loop durable preference marker {marker}"


def memory_search(
    client: httpx.Client,
    env: Env,
    query: str,
    tenant: Tenant | None = None,
) -> list[dict[str, Any]]:
    who = tenant or org_a_tenant(env)
    resp = client.post(
        f"{env.memory}/v1/memories/search",
        headers=_auth_headers(who),
        json={
            "agent_id": who.agent,
            "query": query,
            "limit": 20,
            "min_similarity": 0.0,
        },
    )
    if resp.status_code != 200:
        raise AssertionError(f"search HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json().get("data") or {}
    results = data.get("results") or []
    return results if isinstance(results, list) else []


def _hot_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    items = data.get("memories") or data.get("results") or data.get("items") or []
    return items if isinstance(items, list) else []


def memory_hot(
    client: httpx.Client,
    env: Env,
    tenant: Tenant | None = None,
) -> list[dict[str, Any]]:
    who = tenant or org_a_tenant(env)
    resp = client.get(
        f"{env.memory}/v1/memories/hot",
        headers=_auth_headers(who),
        params={"agent_id": who.agent, "limit": 50},
    )
    if resp.status_code != 200:
        raise AssertionError(f"hot HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json().get("data") or {}
    return _hot_items(data if isinstance(data, dict) else {})


def marker_in_blob(obj: object, marker: str) -> bool:
    return marker in json.dumps(obj)


def marker_present(client: httpx.Client, env: Env, marker: str) -> None:
    query = memory_content(marker)
    if marker_in_blob(memory_search(client, env, query), marker):
        return
    if marker_in_blob(memory_hot(client, env), marker):
        return
    raise AssertionError("marker memory not searchable/hot yet")


def _content_from_item(item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    content = item.get("content")
    if isinstance(content, str):
        return content
    nested = item.get("memory")
    if isinstance(nested, dict) and isinstance(nested.get("content"), str):
        return nested["content"]
    return None


def _first_marker_content(items: list[Any], marker: str) -> str | None:
    for item in items:
        content = _content_from_item(item)
        if content is not None and marker in content:
            return content
    return None


def first_hot_content_with_marker(
    client: httpx.Client, env: Env, marker: str
) -> str | None:
    found = _first_marker_content(memory_hot(client, env), marker)
    if found:
        return found
    return _first_marker_content(memory_search(client, env, marker), marker)


def inject_query_for_marker(client: httpx.Client, env: Env, marker: str) -> str:
    if os.environ.get("IBEX_E2E_P35_LIVE_EXTRACTION") == "1":
        stored = first_hot_content_with_marker(client, env, marker)
        if stored:
            return stored
    return memory_content(marker)


def memories_injected(hdrs: dict[str, str]) -> int:
    raw = hdrs.get("x-ibex-memories-injected", "0")
    try:
        return int(raw)
    except ValueError:
        return 0


def require_grpc() -> None:
    if grpc is None or context_pb2 is None:
        fail("grpc / context_pb2 unavailable — run buf generate + PYTHONPATH")


@dataclass(frozen=True)
class AssembleOpts:
    skip_hot: bool = False
    skip_cold: bool = False


def assemble_once(env: Env, query: str, opts: AssembleOpts | None = None) -> Any:
    require_grpc()
    flags = opts or AssembleOpts()
    channel = grpc.insecure_channel(env.context_addr)
    try:
        method = channel.unary_unary(
            "/ibex.context.v1.ContextAssemblyService/AssembleContext",
            request_serializer=context_pb2.AssembleContextRequest.SerializeToString,
            response_deserializer=context_pb2.AssembleContextResponse.FromString,
        )
        req = context_pb2.AssembleContextRequest(
            org_id=env.org_a,
            agent_id=env.agent_a,
            model="gpt-4o-mini",
            query=query,
            options=context_pb2.AssemblyOptions(
                skip_hot_memories=flags.skip_hot,
                skip_cold_memories=flags.skip_cold,
            ),
        )
        return method(req, timeout=5.0)
    finally:
        channel.close()


def mcp_jsonrpc(
    client: httpx.Client, env: Env, payload: dict[str, Any]
) -> tuple[int, str]:
    headers = {
        "Authorization": f"Bearer {env.auth_token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    resp = client.post(f"{env.mcp}/mcp", headers=headers, json=payload)
    return resp.status_code, resp.text


def percentile(values: list[float], pct: float) -> float:
    """Interpolated percentile; *pct* is a fraction in ``[0, 1]`` (e.g. 0.95).

    Matches the linear-rank approach in ``benchmarks/memory/synth.py`` so p95/p99
    can diverge on small samples. Callers must pass a non-empty list.
    """
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = pct * (len(ordered) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return ordered[lo]
    weight = rank - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


@dataclass(frozen=True)
class ChatResult:
    code: int
    headers: dict[str, str]
    body: object


def assert_injected(result: ChatResult, marker: str, label: str) -> None:
    require_chat_ok(result.code, label)
    if memories_injected(result.headers) < 1 and marker not in json.dumps(result.body):
        raise AssertionError(f"{label}: marker not injected yet")
