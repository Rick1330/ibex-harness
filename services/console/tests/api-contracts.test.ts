import { describe, expect, it } from "vitest"

import { parseOperatorSession, parsePlatformHealth } from "../src/lib/api/contracts"

const session = {
  subject: "user-1",
  org_id: "11111111-1111-4111-8111-111111111111",
  session_id: "session-1",
  permissions: 4,
}

const health = {
  dependency_health: { api: "ok", postgres: "ok", auth: "ok", redis: "ok" },
  last_backup_at: null,
  last_restore_drill: null,
  retention_horizon_days: 90,
  ingestion_lag_seconds: null,
  dlq_depth: 0,
  degraded_mode: false,
  outbox_max_aggregate_seq: 12,
  deploy_image_digest: "sha256:abc",
  observed_at: "2026-09-26T12:00:00.000Z",
}

describe("operator response contracts", () => {
  it("accepts the stable session and health shapes", () => {
    expect(parseOperatorSession(session).org_id).toBe(session.org_id)
    expect(parsePlatformHealth(health).dependency_health.redis).toBe("ok")
  })

  it("rejects unknown session fields", () => {
    expect(() => parseOperatorSession({ ...session, token: "secret" })).toThrow()
  })

  it("rejects malformed tenant identity and health timestamps", () => {
    expect(() => parseOperatorSession({ ...session, org_id: "org-a" })).toThrow()
    expect(() => parsePlatformHealth({ ...health, observed_at: "not-a-time" })).toThrow()
  })
})
