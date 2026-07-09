import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { IbexVideo } from "@/components/landing/ibex-video";

vi.mock("@/hooks/use-ibex-video-crossfade", () => ({
  useIbexVideoCrossfade: () => ({
    aRef: { current: null },
    bRef: { current: null },
    wrapRef: { current: null },
    posterSrc: "/ibex-ascii-poster.webp",
    videoClass: (active: boolean) => (active ? "active" : "inactive"),
    isAActive: true,
    isBActive: false,
  }),
}));

describe("IbexVideo", () => {
  it("renders dual video elements for crossfade", () => {
    const { container } = render(<IbexVideo />);
    const videos = container.querySelectorAll("video");
    expect(videos).toHaveLength(2);
    expect(videos[0]).toHaveAttribute("tabindex", "-1");
  });
});
