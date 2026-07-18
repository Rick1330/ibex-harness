import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/source", () => ({
  roadmapSource: {
    getPages: () => [],
    getPage: () => undefined,
  },
}));

import {
  getPhaseTimeline,
  getPhaseCards,
} from "@/lib/roadmap-hub";

describe("getPhaseTimeline", () => {
  it("returns ordered phases with anchors and display indexes", () => {
    const timeline = getPhaseTimeline();
    expect(timeline.length).toBeGreaterThan(0);
    expect(timeline[0]?.phaseIndex).toBe("0");
    expect(timeline[0]?.anchor).toMatch(/^phase-/);
    expect(timeline.some((p) => p.phaseIndex === "1.5")).toBe(true);
  });

  it("keeps getPhaseCards compatible for existing consumers", () => {
    const cards = getPhaseCards();
    expect(cards.every((c) => typeof c.slug === "string")).toBe(true);
  });
});
