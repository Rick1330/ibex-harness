import { describe, expect, it } from "vitest"
import { ACCESS_KEYS, accessCounts, accessNotes } from "../app/lib/access-preview"

const ROTATION_LEAD = "What is due for rotation."

/** The three notes the Access About disclosure renders regardless of key state. */
const STATIC_LEADS = [
  "Keys are shown by prefix only.",
  "Rotation is a window, not a suggestion.",
  "Role checks are server-side.",
]

function rotationNotes(overdueKeys: number) {
  return accessNotes(overdueKeys).filter((note) => note.lead === ROTATION_LEAD)
}

describe("accessNotes", () => {
  it("omits the rotation note while no key is overdue", () => {
    const notes = accessNotes(0)

    expect(rotationNotes(0)).toHaveLength(0)
    expect(notes.map((note) => note.lead)).toEqual(STATIC_LEADS)
  })

  it("adds exactly one rotation note for a single overdue key, unchanged from the page", () => {
    const notes = accessNotes(1)

    expect(rotationNotes(1)).toEqual([
      {
        lead: ROTATION_LEAD,
        // Copied verbatim from the AccessView body the page rendered before the
        // derivation moved into app/lib/; the e2e caveat test asserts the same
        // sentence through the About disclosure.
        body: "1 live key is past its 30-day rotation window. Rotation and revocation require a privileged write contract.",
      },
    ])
    expect(notes.at(-1)?.lead).toBe(ROTATION_LEAD)
  })

  it("interpolates the overdue count without changing the sentence around it", () => {
    // The fixture-authored sentence has no singular/plural branch: it reads
    // "N live key is" for every count. Preserve it verbatim; a grammatical fix
    // here would change rendered output, which is out of scope for this change.
    expect(rotationNotes(3).map((note) => note.body)).toEqual([
      "3 live key is past its 30-day rotation window. Rotation and revocation require a privileged write contract.",
    ])
    expect(rotationNotes(3)).toHaveLength(1)
  })

  it("keeps the static notes in the same order in every branch", () => {
    for (const overdueKeys of [0, 1, 3]) {
      const leads = accessNotes(overdueKeys)
        .map((note) => note.lead)
        .filter((lead) => lead !== ROTATION_LEAD)

      expect(leads).toEqual(STATIC_LEADS)
    }
  })

  it("treats a negative count as no overdue keys", () => {
    expect(rotationNotes(-1)).toHaveLength(0)
    expect(accessNotes(-1).map((note) => note.lead)).toEqual(STATIC_LEADS)
  })

  it("renders the rotation note for the fixture's overdue keys", () => {
    const counts = accessCounts()

    expect(counts.overdueKeys).toBe(1)
    expect(ACCESS_KEYS.filter((key) => key.state === "overdue")).toHaveLength(1)
    expect(rotationNotes(counts.overdueKeys).map((note) => note.body)).toEqual([
      "1 live key is past its 30-day rotation window. Rotation and revocation require a privileged write contract.",
    ])
    expect(accessNotes(counts.overdueKeys)).toHaveLength(STATIC_LEADS.length + 1)
  })
})
