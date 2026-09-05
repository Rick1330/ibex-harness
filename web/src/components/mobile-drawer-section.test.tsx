import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MobileDrawerSectionContent } from "@/components/mobile-drawer-section";
import type { MobileNavData } from "@/lib/mobile-nav-data";
import type { MobileNavSectionConfig } from "@/lib/site-nav-config";

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

vi.mock("@/components/layout/mobile-page-tree-nav", () => ({
  MobilePageTreeNav: ({
    nodes,
  }: Readonly<{ nodes: ReadonlyArray<{ kind: string; name: string }> }>) => (
    <div data-testid="mobile-page-tree-nav">
      {nodes.map((node) => (
        <div key={node.name}>{node.name}</div>
      ))}
    </div>
  ),
}));

vi.mock("@/components/layout/docs-sidebar", () => ({
  docsSidebarItemClassName: () => "sidebar-item",
}));

const mobileNavData: MobileNavData = {
  docsTree: [],
  roadmapTree: [],
  benchmarkTree: [
    { kind: "page", name: "Overview", url: "/benchmarks" },
    { kind: "page", name: "Suites compare", url: "/benchmarks/suites-compare" },
    {
      kind: "folder",
      name: "Proxy",
      children: [
        { kind: "page", name: "Latency", url: "/benchmarks/latency" },
        { kind: "page", name: "Waterfall", url: "/benchmarks/waterfall" },
      ],
    },
    {
      kind: "folder",
      name: "Memory",
      children: [
        {
          kind: "folder",
          name: "HNSW",
          children: [
            { kind: "page", name: "Overview", url: "/benchmarks/memory" },
          ],
        },
      ],
    },
  ],
  blogPosts: [],
  releasePages: [],
  benchmarkPages: [],
};

const benchmarkSection: MobileNavSectionConfig = {
  id: "benchmarks",
  title: "Benchmarks",
  match: "/benchmarks",
  href: "/benchmarks",
  description: "Proxy and memory performance suites",
  iconId: "benchmarks",
  kind: "tree",
  dataKey: "benchmarkTree",
  baseUrl: "/benchmarks",
};

describe("MobileDrawerSectionContent", () => {
  it("renders the nested benchmark tree (not a flat leaf list)", () => {
    render(
      <MobileDrawerSectionContent
        section={benchmarkSection}
        data={mobileNavData}
        pathname="/benchmarks"
        onClose={() => {}}
      />,
    );

    expect(screen.getByTestId("mobile-page-tree-nav")).toBeInTheDocument();
    expect(screen.getByText("Proxy")).toBeInTheDocument();
    expect(screen.getByText("Memory")).toBeInTheDocument();
    expect(screen.getByText("Suites compare")).toBeInTheDocument();
  });
});
