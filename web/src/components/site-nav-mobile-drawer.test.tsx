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

vi.mock("@/components/layout/mobile-section-switcher", () => ({
  MobileSectionSwitcher: ({
    onSelect,
  }: Readonly<{ onSelect: () => void }>) => (
    <button type="button" onClick={onSelect}>
      Switch section
    </button>
  ),
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
  benchmarkPages: [],
};

afterEach(() => {
  cleanup();
});

async function renderOpenDrawer(onClose = vi.fn()) {
  render(
    <SiteNavMobileDrawer
      open
      onClose={onClose}
      mobileNavData={mobileNavData}
    />,
  );

  await waitFor(() => {
    expect(document.getElementById("site-nav-mobile-drawer")).toBeInTheDocument();
  });

  return onClose;
}

describe("SiteNavMobileDrawer", () => {
  it("mounts the drawer portal when open", async () => {
    await renderOpenDrawer();

    expect(screen.getByTestId("nav-search")).toBeInTheDocument();
  });

  it("calls onClose from the overlay", async () => {
    const onClose = await renderOpenDrawer();

    fireEvent.click(screen.getByLabelText("Close menu"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose from section content", async () => {
    const onClose = await renderOpenDrawer();

    fireEvent.click(screen.getByRole("button", { name: "Close section" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
