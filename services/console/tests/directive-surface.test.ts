import { describe, expect, it } from "vitest"

import {
  directiveStateLabel,
  formatBytes,
  mostUsedVersion,
  sessionsOffPointer,
  versionByNumber,
} from "../app/lib/directive-summary"
import { SURFACES } from "../shared/operator/surfaces"
import type { OperatorDirectiveDetail } from "../shared/operator/contracts"

const detail = {
  id: "11111111-1111-4111-8111-111111111111",
  agent_id: "22222222-2222-4222-8222-222222222222",
  agent_name: "Support triage",
  agent_slug: "support-triage",
  is_active: true,
  injection_mode: "system_first",
  active_version_num: 2,
  version_count: 3,
  last_version_at: "2026-11-01T12:00:00.000Z",
  updated_at: "2026-11-02T12:00:00.000Z",
  versions: [
    {
      version_num: 3,
      content_digest: "abcdef012345",
      content_bytes: 2048,
      created_by: null,
      created_at: "2026-11-01T12:00:00.000Z",
      is_live: false,
    },
    {
      version_num: 2,
      content_digest: "fedcba543210",
      content_bytes: 1024,
      created_by: null,
      created_at: "2026-10-30T12:00:00.000Z",
      is_live: true,
    },
  ],
  usage: [
    { version_num: 3, sessions: 40, last_session_at: "2026-11-01T13:00:00.000Z" },
    { version_num: 2, sessions: 120, last_session_at: "2026-11-02T11:00:00.000Z" },
  ],
  usage_range: "7d",
  usage_window_start: "2026-10-26T12:00:00.000Z",
  active_version_missing: false,
} as OperatorDirectiveDetail

describe("directives live contract", () => {
  it("is live with the versions contract", () => {
    expect(SURFACES.directives.availability).toBe("live")
    expect(SURFACES.directives.contract).toBe("operator.directives.versions.v1")
  })

  it("does not claim content, diffs, or promotion history", () => {
    for (const text of [
      SURFACES.directives.description,
      SURFACES.directives.question,
    ]) {
      expect(text).not.toContain("NEEDS-BACKEND")
      expect(text.toLowerCase()).not.toContain("planned")
    }
    expect(SURFACES.directives.description.toLowerCase()).not.toContain("diff shown")
  })

  it("reads the pointer as live, not the newest version", () => {
    // A rollback leaves v3 newest and v2 live; the UI must not say "v3 live".
    expect(versionByNumber(detail, detail.active_version_num)?.version_num).toBe(2)
    expect(mostUsedVersion(detail)?.version_num).toBe(2)
    expect(sessionsOffPointer(detail)).toBe(40)
    expect(
      directiveStateLabel({ ...detail, active_version_num: 2, is_active: true }),
    ).toBe("Live v2")
    expect(directiveStateLabel({ ...detail, is_active: false })).toBe("Inactive")
    expect(formatBytes(2048)).toBe("2.0 KiB")
  })
})
