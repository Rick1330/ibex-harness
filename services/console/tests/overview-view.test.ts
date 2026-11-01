import { describe, expect, it } from "vitest"

import {
  OVERVIEW_RUNS_LIMIT,
  buildOverviewAttention,
  buildOverviewSources,
  overviewStaleness,
  overviewTiles,
  overviewVerdict,
} from "../app/lib/overview-view"
import type {
  PublicOperatorContext,
  PublicOperatorOverview,
  PublicOperatorTrace,
  PublicOperatorTraceList,
  PublicPlatformHealth,
} from "../shared/operator/public"

/** The Overview reads live data, so every age here is measured against a clock the test owns. */
const NOW = Date.parse("2026-10-30T15:12:00Z")
const FRESH = "2026-10-30T15:11:40Z"
const STALE = "2026-10-30T14:00:00Z"

function health(overrides: Partial<PublicPlatformHealth> = {}): PublicPlatformHealth {
  return {
    dependency_health: { postgres: "ok", redis: "ok" },
    last_backup_at: "2026-10-29T02:00:00Z",
    last_restore_drill: { completed_at: "2026-10-20T03:00:00Z", duration_seconds: 1_440 },
    retention_horizon_days: 90,
    ingestion_lag_seconds: 3,
    dlq_depth: 0,
    degraded_mode: false,
    outbox_max_aggregate_seq: 41,
    deploy_image_digest: "sha256:1f2c3d",
    observed_at: FRESH,
    ...overrides,
  }
}

function trace(overrides: Partial<PublicOperatorTrace> = {}): PublicOperatorTrace {
  return {
    trace_id: "trace-a",
    run_id: "11111111-1111-4111-8111-111111111111",
    request_id: "request-a",
    agent_id: null,
    session_id: null,
    checkpoint_id: null,
    status: "ok",
    error_code: null,
    started_at: "2026-10-30T15:10:00Z",
    ended_at: "2026-10-30T15:10:01Z",
    duration_ms: 1_000,
    evidence: {
      schema_version: "evidence.v1",
      capture_mode: "full",
      completeness: "complete",
      sample_decision: "kept",
      freshness: "fresh",
      retention: "unknown",
      source: "postgres.evidence_runs",
      source_watermark: "outbox:41",
      publication_state: "published",
      ingestion_lag_ms: 1_200,
      policy_version: "operator.trace-read.v1",
      observed_at: FRESH,
    },
    ...overrides,
  }
}

function list(items: PublicOperatorTrace[], overrides: Partial<PublicOperatorTraceList> = {}): PublicOperatorTraceList {
  return {
    schema_version: "operator.trace-list.v1",
    query_grammar_version: "operator.trace-query.v1",
    items,
    next_cursor: null,
    truncated: false,
    matched_count: null,
    returned_count: items.length,
    observed_at: FRESH,
    query_start: "2026-10-30T14:12:00Z",
    query_end: FRESH,
    limit: OVERVIEW_RUNS_LIMIT,
    ...overrides,
  }
}

function attention(
  healthValue: PublicPlatformHealth | null,
  traces: PublicOperatorTraceList | null,
  options: { healthFailed?: boolean; tracesFailed?: boolean } = {},
) {
  return buildOverviewAttention({
    health: healthValue,
    traces,
    staleness: overviewStaleness(healthValue?.observed_at ?? null, NOW),
    healthFailed: options.healthFailed ?? false,
    tracesFailed: options.tracesFailed ?? false,
  })
}

describe("overview attention", () => {
  it("raises no finding when every reported field is in order", () => {
    expect(attention(health(), list([trace()]))).toEqual([])
  })

  it("maps dependency status onto the product severity vocabulary and orders by it", () => {
    const rows = attention(
      health({ dependency_health: { auth_grpc: "ok", redis: "degraded", postgres: "unavailable" } }),
      null,
    )
    expect(rows.map((row) => [row.severity, row.id])).toEqual([
      ["critical", "dependency:postgres"],
      ["warning", "dependency:redis"],
    ])
    expect(rows[0]?.title).toBe("Postgres reported unavailable")
    expect(rows[0]?.link?.href).toBe("/platform")
  })

  it("reports degraded mode and dead-letter depth separately from the checks", () => {
    const rows = attention(health({ degraded_mode: true, dlq_depth: 2 }), null)
    const ids = rows.map((row) => row.id)
    expect(ids).toContain("degraded-mode")
    expect(ids).toContain("dlq")
    expect(rows.find((row) => row.id === "dlq")?.link?.href).toBe("/platform?tab=pipeline")
  })

  it("groups fields the snapshot returned as null instead of filling them in", () => {
    const rows = attention(
      health({ last_backup_at: null, last_restore_drill: null, deploy_image_digest: null, outbox_max_aggregate_seq: null }),
      null,
    )
    const row = rows.find((entry) => entry.id === "recovery-unrecorded")
    expect(row?.severity).toBe("info")
    expect(row?.title).toBe(
      "Recovery and chain evidence not recorded: last backup, restore drill, deployed image digest, outbox watermark",
    )
  })

  it("scopes every run finding to the page that was read, never the organization", () => {
    const failing = trace({
      run_id: "22222222-2222-4222-8222-222222222222",
      trace_id: "trace-b",
      status: "error",
      evidence: {
        ...trace().evidence,
        completeness: "partial",
        publication_state: "failed",
      },
    })
    const rows = attention(health(), list([trace(), failing]))
    const titles = rows.map((row) => row.title)
    expect(titles).toContain("1 of 2 runs on this page reported an error")
    expect(titles).toContain("1 of 2 runs on this page have a broken evidence publication")
    expect(titles).toContain("1 of 2 runs on this page recorded an incomplete record")
    expect(rows.find((row) => row.id === "runs-failed")?.link?.href).toBe("/explore?status=error")
  })

  it("says a page is a page only when the source reports no matched total", () => {
    const truncated = list([trace()], { truncated: true, matched_count: 12 })
    expect(attention(health(), truncated).map((row) => row.id)).not.toContain("runs-scope")
    expect(attention(health(), list([trace()], { truncated: true })).map((row) => row.id)).toContain("runs-scope")
  })

  it("marks a stale snapshot as a finding without inventing a newer one", () => {
    const rows = buildOverviewAttention({
      health: health({ observed_at: STALE }),
      traces: null,
      staleness: overviewStaleness(STALE, NOW),
      healthFailed: false,
      tracesFailed: false,
    })
    expect(rows.map((row) => row.id)).toContain("stale-snapshot")
    expect(rows.find((row) => row.id === "stale-snapshot")?.severity).toBe("warning")
  })

  it("counts an unread source as a finding rather than a clean report", () => {
    const rows = attention(null, null, { healthFailed: true, tracesFailed: true })
    expect(rows.map((row) => row.id).sort()).toEqual(["health-unread", "traces-unread"])
  })
})

describe("overview verdict and tiles", () => {
  const flags = {
    hasOverview: true,
    hasHealth: true,
    hasTraces: true,
    authIssue: false,
    loading: false,
  }

  function verdict(
    overrides: Partial<typeof flags>,
    issues: ReturnType<typeof buildOverviewAttention>,
    healthValue: PublicPlatformHealth | null = health(),
  ) {
    return overviewVerdict({
      flags: { ...flags, ...overrides },
      issues,
      health: healthValue,
      staleness: overviewStaleness(FRESH, NOW),
    })
  }

  it("stays open instead of assuming healthy while health is unread", () => {
    const result = verdict({ hasHealth: false }, [])
    expect(result.tone).toBe("muted")
    expect(result.caveat).toBe("Verdict stays open")
  })

  it("reports an unreported snapshot without substituting a sample organization", () => {
    const result = verdict({ hasOverview: false }, [])
    expect(result.tone).toBe("warning")
    expect(result.text).toBe("Organization snapshot unavailable.")
  })

  it("calls a clean read an observation, not a certification", () => {
    const result = verdict({}, [])
    expect(result.tone).toBe("ok")
    expect(result.caveat).toBe("Observation, not certification")
    expect(result.text).toContain("2 dependencies")
  })

  it("keeps tiles unreported when a source did not resolve", () => {
    const tiles = overviewTiles({ overview: null, health: null, traces: null })
    expect(tiles.map((tile) => tile.value)).toEqual(["Not reported", "Not reported", "Not reported", "Not reported"])
  })

  it("only counts runs that the list itself reported", () => {
    const tiles = overviewTiles({
      overview: {
        schema_version: "operator.overview.v1",
        org_name: "Northwind",
        org_slug: "org_demo_42",
        org_status: "active",
        counts: { active_users: 4, agents: 9, active_agents: 6 },
        observed_at: FRESH,
        completeness: "complete",
      } satisfies PublicOperatorOverview,
      health: health({ dependency_health: { postgres: "ok", redis: "degraded" } }),
      traces: list([trace(), trace()]),
    })
    expect(tiles[0]?.value).toBe("9")
    expect(tiles[2]?.value).toBe("1 of 2")
    expect(tiles[2]?.tone).toBe("warning")
    expect(tiles[3]?.value).toBe("2")
    expect(tiles[3]?.helper).toBe("No matched total reported by the source.")
  })
})

describe("overview sources", () => {
  function sources(overrides: Partial<Parameters<typeof buildOverviewSources>[0]> = {}) {
    return buildOverviewSources({
      context: {
        schema_version: "operator.context.v1",
        org_name: "Northwind",
        org_slug: "org_demo_42",
        org_status: "active",
        observed_at: FRESH,
        role: "admin",
      } satisfies PublicOperatorContext,
      overview: null,
      health: health(),
      traces: null,
      healthFailed: false,
      tracesFailed: false,
      loading: false,
      ...overrides,
    })
  }

  it("reports each source's own state instead of the page's best guess", () => {
    const rows = sources({ overview: null })
    expect(rows.map((row) => [row.id, row.state])).toEqual([
      ["context", "ok"],
      ["overview", "missing"],
      ["health", "ok"],
      ["traces", "missing"],
    ])
  })

  it("keeps an empty dependency report from reading as healthy", () => {
    const rows = sources({ health: health({ dependency_health: {} }), overview: null })
    const healthRow = rows.find((row) => row.id === "health")
    expect(healthRow?.state).toBe("ok")
    expect(healthRow?.detail).toBe("The snapshot resolved but reported no dependency checks. An empty report is not a healthy report.")
  })

  it("shows a source that is still being read as pending", () => {
    const rows = sources({ loading: true })
    expect(rows.find((row) => row.id === "overview")?.state).toBe("pending")
  })
})
