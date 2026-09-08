#!/usr/bin/env python3
"""Phase 3.5 learning-loop e2e scenarios (3.5.F.1).

Polls observable side effects with eventually() — no sleep-only waits.
Helpers live in e2e_phase35_lib.py (CodeScene complexity budget).
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

# Allow `python infra/scripts/e2e_phase35_scenarios.py` without PYTHONPATH hacks.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from e2e_phase35_lib import (  # noqa: E402
    AssembleOpts,
    ChatOpts,
    ChatResult,
    Env,
    assert_injected,
    assemble_once,
    chat,
    env_from_os,
    eventually,
    fail,
    inject_query_for_marker,
    marker_in_blob,
    marker_present,
    mcp_jsonrpc,
    memories_injected,
    memory_content,
    memory_hot,
    memory_search,
    org_b_tenant,
    pass_,
    percentile,
    require_chat_ok,
    require_grpc,
    terminate,
)


def _require_http_ok(code: int, label: str) -> None:
    if code != 200:
        fail(f"{label} HTTP {code}")


def _warm_and_terminate(client: httpx.Client, env: Env) -> None:
    code, hdrs, _ = chat(
        client, env, f"phase35 warm turn zero remember later {env.marker}"
    )
    _require_http_ok(code, "scenario1 warm chat")
    session_id = hdrs.get("x-ibex-session-id") or ""
    if not session_id:
        fail("scenario1 missing X-IBEX-Session-ID")
    code, _, _ = chat(
        client,
        env,
        f"Please remember my preference marker {env.marker} forever.",
        ChatOpts(session_id=session_id),
    )
    _require_http_ok(code, "scenario1 second chat")
    if terminate(client, env, session_id) != 200:
        fail("scenario1 terminate HTTP not 200")


def scenario_1(client: httpx.Client, env: Env) -> None:
    """Extract → inject closed loop; prove turns + extraction fired."""
    _warm_and_terminate(client, env)
    eventually(
        lambda: marker_present(client, env, env.marker),
        timeout=env.timeout_s,
        interval=env.interval_s,
        label="scenario1 extraction→memory",
    )
    pass_("scenario1 extraction wrote searchable marker memory")

    def _injected() -> None:
        code, hdrs, body = chat(
            client, env, inject_query_for_marker(client, env, env.marker)
        )
        assert_injected(ChatResult(code, hdrs, body), env.marker, "inject chat")

    eventually(
        _injected,
        timeout=env.timeout_s,
        interval=max(env.interval_s, 0.75),
        label="scenario1 chat inject",
    )
    pass_("scenario1 next chat injects extracted memory")


def _org_b_chat_leaked(marker: str, hdrs: dict[str, str], body: object) -> bool:
    if memories_injected(hdrs) < 1:
        return False
    return marker in json.dumps(body)


def _assert_org_b_isolated(client: httpx.Client, env: Env) -> None:
    tenant_b = org_b_tenant(env)
    code, hdrs, body = chat(
        client, env, memory_content(env.marker), ChatOpts(tenant=tenant_b)
    )
    require_chat_ok(code, "org B chat")
    if _org_b_chat_leaked(env.marker, hdrs, body):
        raise AssertionError("Org A marker leaked into Org B chat body")
    results = memory_search(client, env, memory_content(env.marker), tenant_b)
    if marker_in_blob(results, env.marker):
        raise AssertionError("Org A marker searchable as Org B")
    if marker_in_blob(memory_hot(client, env, tenant_b), env.marker):
        raise AssertionError("Org A marker in Org B hot cache")


def scenario_2(client: httpx.Client, env: Env) -> None:
    """Thin Org A / Org B isolation smoke."""
    eventually(
        lambda: _assert_org_b_isolated(client, env),
        timeout=min(30.0, env.timeout_s),
        interval=env.interval_s,
        label="scenario2 cross-tenant",
    )
    pass_("scenario2 Org A marker absent from Org B context/search")


def scenario_3(env: Env) -> None:
    """20 concurrent Assemble — record p95/p99; hard-gate mechanism only."""
    require_grpc()
    latencies: list[float] = []
    errors = 0

    def _one(_: int) -> float:
        import time

        started = time.perf_counter()
        resp = assemble_once(env, env.marker)
        if resp.metrics is None:
            raise AssertionError("missing AssemblyMetrics")
        _ = resp.metrics.candidates_evaluated
        return (time.perf_counter() - started) * 1000.0

    with ThreadPoolExecutor(max_workers=20) as pool:
        futs = [pool.submit(_one, i) for i in range(20)]
        for fut in as_completed(futs):
            try:
                latencies.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                errors += 1
                print(f"scenario3 assemble error: {exc!r}", file=sys.stderr)

    if errors or len(latencies) < 20:
        fail(f"scenario3 incomplete ({errors} errors, n={len(latencies)})")
    print(
        json.dumps(
            {
                "scenario": 3,
                "n": len(latencies),
                "mean_ms": round(statistics.fmean(latencies), 3),
                "p95_ms": round(percentile(latencies, 0.95), 3),
                "p99_ms": round(percentile(latencies, 0.99), 3),
                "note": "soft threshold; mechanism-gated only",
            }
        )
    )
    pass_("scenario3 Assemble concurrency mechanism OK (latency printed)")


def _ibex_meta(body: object) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {}
    meta = body.get("ibex")
    return meta if isinstance(meta, dict) else {}


def _scenario4_sample(client: httpx.Client, env: Env, index: int) -> dict[str, Any]:
    code, hdrs, body = chat(
        client, env, f"phase35 overhead probe {index} about {env.marker}"
    )
    require_chat_ok(code, "scenario4 chat")
    has_fallback = "x-ibex-context-fallback" in hdrs
    has_injected = "x-ibex-memories-injected" in hdrs
    if not has_fallback and not has_injected:
        raise AssertionError(
            "scenario4 missing context headers (is IBEX_CONTEXT_ENABLED?)"
        )
    ibex = _ibex_meta(body)
    return {
        "fallback": hdrs.get("x-ibex-context-fallback"),
        "memories_injected": memories_injected(hdrs),
        "context_assembly_ms": ibex.get("context_assembly_ms"),
        "proxy_overhead_ms": ibex.get("proxy_overhead_ms"),
    }


def _numeric_field(samples: list[dict[str, Any]], key: str) -> list[float]:
    out: list[float] = []
    for sample in samples:
        raw = sample.get(key)
        if isinstance(raw, (int, float)):
            out.append(float(raw))
    return out


def scenario_4(client: httpx.Client, env: Env) -> None:
    """Proxy chat with Assemble — capture overhead/assembly ms when present."""
    samples: list[dict[str, Any]] = []

    def _collect() -> None:
        samples.clear()
        for i in range(10):
            samples.append(_scenario4_sample(client, env, i))

    eventually(
        _collect,
        timeout=env.timeout_s,
        interval=max(env.interval_s, 0.5),
        label="scenario4 chat samples",
    )
    overheads = _numeric_field(samples, "proxy_overhead_ms")
    assemblies = _numeric_field(samples, "context_assembly_ms")
    report: dict[str, Any] = {
        "scenario": 4,
        "samples": len(samples),
        "note": "soft threshold; mechanism-gated only",
    }
    if overheads:
        report["proxy_overhead_p95_ms"] = round(percentile(overheads, 0.95), 3)
        report["proxy_overhead_p99_ms"] = round(percentile(overheads, 0.99), 3)
    if assemblies:
        report["context_assembly_p95_ms"] = round(percentile(assemblies, 0.95), 3)
    print(json.dumps(report))
    pass_("scenario4 proxy Assemble path headers present (latency printed)")


def _ladder_counts_nonzero(candidates: int, included: int) -> bool:
    if candidates != 0:
        return True
    return included != 0


def _assert_ladder_metrics(
    label: str,
    resp: Any,
    *,
    expect_zero: bool,
    require_candidates: bool = False,
) -> dict[str, int]:
    if resp.metrics is None:
        fail(f"{label} missing metrics")
    candidates = int(resp.metrics.candidates_evaluated)
    included = int(resp.memories_included)
    if expect_zero and _ladder_counts_nonzero(candidates, included):
        fail(f"{label} expected zeros got candidates={candidates} included={included}")
    if require_candidates and candidates < 1:
        raise AssertionError(
            f"{label} expected candidates_evaluated > 0 got {candidates} "
            f"(memories_included={included})"
        )
    pass_(f"{label} candidates={candidates} memories_included={included}")
    return {"candidates_evaluated": candidates, "memories_included": included}


def _scenario5_l3(client: httpx.Client, env: Env) -> None:
    if env.context_pid is None:
        fail("scenario5 L3 requires IBEX_E2E_P35_CONTEXT_PID to pause context")
    os.kill(env.context_pid, signal.SIGSTOP)
    try:
        code, hdrs, _ = chat(client, env, "phase35 L3 fallback probe")
        _require_http_ok(code, "scenario5 L3 chat (want 200 fail-open)")
        if hdrs.get("x-ibex-context-fallback") != "true":
            fail(
                f"scenario5 L3 want X-IBEX-Context-Fallback=true "
                f"got {hdrs.get('x-ibex-context-fallback')!r}"
            )
    finally:
        os.kill(env.context_pid, signal.SIGCONT)
        eventually(
            lambda: assemble_once(env, "warmup"),
            timeout=30.0,
            interval=0.25,
            label="scenario5 context resume",
        )
    pass_("scenario5 L3 proxy X-IBEX-Context-Fallback=true")


def scenario_5(client: httpx.Client, env: Env) -> None:
    """ADR-0071 ladder: L0–L2 via gRPC options/metrics; L3 via proxy Fallback header.

    L0/L1 must observe real retrieval (candidates_evaluated > 0) after scenario 1
    wrote the marker memory — not a metrics-present greenwash.
    L1 uses skip_cold (hot-only), matching ADR-0071 “exactly one source usable.”
    """
    require_grpc()
    query = memory_content(env.marker)
    legs: dict[str, Any] = {}

    def _l0() -> None:
        legs["L0"] = _assert_ladder_metrics(
            "scenario5 L0",
            assemble_once(env, query),
            expect_zero=False,
            require_candidates=True,
        )

    def _l1() -> None:
        legs["L1"] = _assert_ladder_metrics(
            "scenario5 L1 skip_cold",
            assemble_once(env, query, AssembleOpts(skip_cold=True)),
            expect_zero=False,
            require_candidates=True,
        )

    eventually(_l0, timeout=env.timeout_s, interval=env.interval_s, label="scenario5 L0")
    eventually(_l1, timeout=env.timeout_s, interval=env.interval_s, label="scenario5 L1")
    legs["L2"] = _assert_ladder_metrics(
        "scenario5 L2 skip_hot+skip_cold",
        assemble_once(env, query, AssembleOpts(skip_hot=True, skip_cold=True)),
        expect_zero=True,
    )
    _scenario5_l3(client, env)
    print(
        json.dumps(
            {
                "scenario": 5,
                "legs": legs,
                "note": "L0/L1 require candidates_evaluated>0; L2 hard zeros; L3 Fallback",
            }
        )
    )


def _mcp_write_memory(client: httpx.Client, env: Env, content: str) -> None:
    code, _ = mcp_jsonrpc(
        client,
        env,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "e2e-phase35", "version": "0"},
            },
        },
    )
    if code not in {200, 202}:
        fail(f"scenario6 mcp initialize HTTP {code}")
    mcp_jsonrpc(
        client, env, {"jsonrpc": "2.0", "method": "notifications/initialized"}
    )
    code, text = mcp_jsonrpc(
        client,
        env,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "write_memory",
                "arguments": {
                    "content": content,
                    "category": "preference",
                    "agent_id": env.agent_a,
                },
            },
        },
    )
    if code not in {200, 202}:
        fail(f"scenario6 write_memory HTTP {code}: {text[:300]}")
    compact = text.replace(" ", "")
    if "isError" in text and '"isError":false' not in compact:
        fail(f"scenario6 write_memory isError: {text[:400]}")


def scenario_6(client: httpx.Client, env: Env) -> None:
    """MCP write_memory → proxy chat inject (shared substrate)."""
    content = memory_content(env.mcp_marker)
    _mcp_write_memory(client, env, content)
    eventually(
        lambda: marker_present(client, env, env.mcp_marker),
        timeout=env.timeout_s,
        interval=env.interval_s,
        label="scenario6 memory durable",
    )

    def _injected() -> None:
        code, hdrs, body = chat(client, env, content)
        assert_injected(ChatResult(code, hdrs, body), env.mcp_marker, "scenario6 chat")

    eventually(
        _injected,
        timeout=env.timeout_s,
        interval=max(env.interval_s, 0.75),
        label="scenario6 proxy inject",
    )
    pass_("scenario6 MCP write → proxy chat inject")


def _parse_want(only: str) -> set[int]:
    parsed = {int(x) for x in only.split(",") if x.strip().isdigit()}
    return parsed or {1, 2, 3, 4, 5, 6}


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3.5 learning-loop scenarios")
    parser.add_argument("--only", default="", help="Comma-separated scenario numbers")
    args = parser.parse_args()
    if "IBEX_E2E_P35_MARKER" not in os.environ:
        fail("IBEX_E2E_P35_MARKER required")
    env = env_from_os()
    want = _parse_want(args.only)
    _ = urlparse(env.proxy)

    runners = {
        1: lambda c: scenario_1(c, env),
        2: lambda c: scenario_2(c, env),
        3: lambda _c: scenario_3(env),
        4: lambda c: scenario_4(c, env),
        5: lambda c: scenario_5(c, env),
        6: lambda c: scenario_6(c, env),
    }
    with httpx.Client(timeout=60.0) as client:
        for num in sorted(want):
            runners[num](client)

    print("")
    print("e2e-phase35 scenarios passed")


if __name__ == "__main__":
    main()
