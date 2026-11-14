import { describe, expect, it } from "vitest"

import { primaryNavigation } from "../app/lib/navigation"

describe("sidebar preview marker", () => {
  it("marks exactly the two core preview surfaces", () => {
    // The sidebar chip renders from this same `availability` field, so the
    // navigation set is the behavioural assertion here; the rendered marker is a
    // visual-review item for the e2e/visual path, not a source string match.
    const preview = primaryNavigation
      .flatMap((group) => group.items)
      .filter((item) => item.availability === "preview")
      .map((item) => item.label)
      .sort()

    expect(preview).toEqual(["Policies", "Settings"])
  })
})
