import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MobilePageTreeNav } from "@/components/layout/mobile-page-tree-nav";
import type { MobileNavNode } from "@/lib/mobile-nav-data";

vi.mock("next/navigation", () => ({
  usePathname: () => "/roadmap/phase-2-single-provider",
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    prefetch: _prefetch,
    ...props
  }: Readonly<{
    href: string;
    children: React.ReactNode;
    prefetch?: boolean;
  }>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/components/layout/path-synced-sidebar-folder", () => ({
  PathSyncedSidebarFolder: ({
    children,
    header,
  }: Readonly<{
    children: React.ReactNode;
    header: React.ReactNode;
  }>) => (
    <section>
      <div>{header}</div>
      {children}
    </section>
  ),
}));

vi.mock("@/components/layout/docs-sidebar", () => ({
  docsNestedFolderHeaderClassName: "nested-folder-header",
  docsSectionHeaderClassName: "section-header",
  docsSidebarItemClassName: () => "sidebar-item",
}));

vi.mock("@/lib/sidebar-page-icon", () => ({
  resolveLeafNavIcon: () => null,
}));

const roadmapNodes: MobileNavNode[] = [
  {
    kind: "folder",
    name: "Phase 2",
    children: [
      {
        kind: "page",
        name: "Overview",
        url: "/roadmap/phase-2-single-provider",
      },
      {
        kind: "page",
        name: "Overview duplicate",
        url: "/roadmap/phase-2-single-provider",
      },
    ],
  },
];

describe("MobilePageTreeNav", () => {
  it("does not emit duplicate React key warnings for repeated page urls", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    render(<MobilePageTreeNav nodes={roadmapNodes} baseUrl="/roadmap" />);

    expect(consoleError).not.toHaveBeenCalledWith(
      expect.stringContaining("Encountered two children with the same key"),
      expect.anything(),
    );

    consoleError.mockRestore();
  });
});
