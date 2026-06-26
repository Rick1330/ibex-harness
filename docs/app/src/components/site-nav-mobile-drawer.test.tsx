import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SiteNavMobileDrawer } from "@/components/site-nav-mobile-drawer";
import type { MobileNavData } from "@/lib/mobile-nav-data";

vi.mock("next/navigation", () => ({
  usePathname: () => "/docs/getting-started/introduction",
}));

vi.mock("@/components/layout/nav-search", () => ({
  NavSearch: () => <div data-testid="nav-search" />,
}));

vi.mock("@/components/mobile-drawer-section", () => ({
  MobileDrawerSectionContent: ({
    onClose,
  }: Readonly<{ onClose: () => void }>) => (
    <button type="button" onClick={onClose}>
      Close section
    </button>
  ),
}));

const mobileNavData: MobileNavData = {
  docsTree: [],
  roadmapTree: [],
  blogPosts: [],
  releasePages: [],
};

afterEach(() => {
  cleanup();
});

describe("SiteNavMobileDrawer", () => {
  it("mounts the drawer portal when open", async () => {
    render(
      <SiteNavMobileDrawer
        open
        onClose={vi.fn()}
        mobileNavData={mobileNavData}
      />,
    );

    await waitFor(() => {
      expect(document.getElementById("site-nav-mobile-drawer")).toBeInTheDocument();
    });
  });

  it("calls onClose from the overlay", async () => {
    const onClose = vi.fn();

    render(
      <SiteNavMobileDrawer
        open
        onClose={onClose}
        mobileNavData={mobileNavData}
      />,
    );

    await waitFor(() => {
      expect(screen.getByLabelText("Close menu")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText("Close menu"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose from section content", async () => {
    const onClose = vi.fn();

    render(
      <SiteNavMobileDrawer
        open
        onClose={onClose}
        mobileNavData={mobileNavData}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Close section" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Close section" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
