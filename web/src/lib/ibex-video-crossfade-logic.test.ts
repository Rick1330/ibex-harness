import { describe, expect, it } from "vitest";

import { loopEndSeconds, secondsUntilLoopEnd } from "./ibex-video-crossfade-logic";

function mockVideo(duration: number, currentTime: number): HTMLVideoElement {
  return { duration, currentTime } as HTMLVideoElement;
}

describe("ibex-video-crossfade-logic", () => {
  it("uses full duration by default", () => {
    const video = mockVideo(10.066, 0);
    expect(loopEndSeconds(video)).toBe(10.066);
    expect(secondsUntilLoopEnd(video)).toBe(10.066);
  });

  it("respects explicit loop end when provided", () => {
    const video = mockVideo(10.066, 1);
    expect(loopEndSeconds(video, 5)).toBe(5);
    expect(secondsUntilLoopEnd(video, 5)).toBeCloseTo(4);
  });

  it("returns infinity when duration is unknown", () => {
    const video = mockVideo(Number.NaN, 0);
    expect(loopEndSeconds(video)).toBe(0);
    expect(secondsUntilLoopEnd(video)).toBe(Number.POSITIVE_INFINITY);
  });
});
