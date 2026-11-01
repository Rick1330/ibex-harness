import { describe, expect, it } from "vitest"

import {
  platformDependencyCounts,
  platformDependencyEntries,
  platformDependencyName,
  platformDependencyStatusLabel,
  platformReadinessState,
  sortPlatformDependencies,
  type PlatformDependencyEntry,
} from "../app/lib/platform-readiness"
import type { PublicPlatformHealth } from "../shared/operator/public"

function health(overrides: Partial<PublicPlatformHealth> = {}): PublicPlatformHealth {
  return {
    dependency_health: { postgres: "ok", redis: "degraded" },
    last_backup_at: null,
    last_restore_drill: null,
    retention_horizon_days: 90,
    ingestion_lag_seconds: null,
    dlq_depth: null,
    degraded_mode: false,
    outbox_max_aggregate_seq: null,
    deploy_image_digest: null,
    observed_at: "2026-10-26T14:02:11Z",
    ...overrides,
  }
}

describe("platform readiness", () => {
  it("distinguishes session, loading, and unavailable states without a report", () => {
    expect(platformReadinessState({ health: null, authIssue: true, loading: false })).toBe("auth")
    expect(platformReadinessState({ health: null, authIssue: false, loading: true })).toBe("loading")
    expect(platformReadinessState({ health: null, authIssue: false, loading: false })).toBe(
      "unavailable",
    )
  })

  it("does not treat an empty dependency report as healthy", () => {
    expect(
      platformReadinessState({
        health: health({ dependency_health: {} }),
        authIssue: false,
        loading: false,
      }),
    ).toBe("no-checks")
  })

  it("treats an unavailable dependency as blocked regardless of degraded_mode", () => {
    expect(
      platformReadinessState({
        health: health({
          dependency_health: { postgres: "ok", redis: "unavailable" },
          degraded_mode: false,
        }),
        authIssue: false,
        loading: false,
      }),
    ).toBe("blocked")
  })

  it("treats degraded_mode or a degraded dependency as degraded", () => {
    expect(
      platformReadinessState({
        health: health({ degraded_mode: true }),
        authIssue: false,
        loading: false,
      }),
    ).toBe("degraded")
    expect(
      platformReadinessState({
        health: health({ dependency_health: { postgres: "degraded" }, degraded_mode: false }),
        authIssue: false,
        loading: false,
      }),
    ).toBe("degraded")
  })

  it("is ready only when every reported check is ok and degraded mode is off", () => {
    expect(
      platformReadinessState({
        health: health({ dependency_health: { postgres: "ok", redis: "ok" } }),
        authIssue: false,
        loading: false,
      }),
    ).toBe("ready")
  })

  it("counts every dependency status", () => {
    const entries = platformDependencyEntries(
      health({
        dependency_health: { api: "ok", auth: "ok", postgres: "unavailable", redis: "degraded" },
      }),
    )
    expect(platformDependencyCounts(entries)).toEqual({
      total: 4,
      ok: 2,
      degraded: 1,
      unavailable: 1,
    })
  })

  it("orders dependencies by severity, then name", () => {
    const entries: PlatformDependencyEntry[] = [
      ["redis", "ok"],
      ["auth", "degraded"],
      ["postgres", "unavailable"],
      ["api", "ok"],
    ]
    expect(sortPlatformDependencies(entries)).toEqual([
      ["postgres", "unavailable"],
      ["auth", "degraded"],
      ["api", "ok"],
      ["redis", "ok"],
    ])
  })

  it("formats dependency names and status labels", () => {
    expect(platformDependencyName("auth_grpc")).toBe("Auth gRPC")
    expect(platformDependencyName("context_grpc")).toBe("Context gRPC")
    expect(platformDependencyName("clickhouse")).toBe("ClickHouse")
    expect(platformDependencyStatusLabel("ok")).toBe("Ok")
    expect(platformDependencyStatusLabel("degraded")).toBe("Degraded")
    expect(platformDependencyStatusLabel("unavailable")).toBe("Unavailable")
  })
})
