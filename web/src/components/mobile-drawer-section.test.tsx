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
  MobilePageTreeNav: () => <div data-testid="mobile-page-tree-nav" />,
}));

vi.mock("@/components/layout/docs-sidebar", () => ({
  docsSidebarItemClassName: () => "sidebar-item",
}));

const mobileNavData: MobileNavData = {
  docsTree: [],
  roadmapTree: [],
  blogPosts: [],
  releasePages: [],
  benchmarkPages: [
    { url: "/benchmarks", title: "Overview" },
    { url: "/benchmarks/latency", title: "Latency" },
    { url: "/benchmarks/waterfall", title: "Waterfall" },
    { url: "/benchmarks/load", title: "Load test" },
    { url: "/benchmarks/history", title: "History" },
    { url: "/benchmarks/compare", title: "Compare" },
  ],
};

const benchmarkSection: MobileNavSectionConfig = {
  id: "benchmarks",
  title: "Benchmarks",
  match: "/benchmarks",
  href: "/benchmarks",
  description: "Proxy performance and regression",
  iconId: "benchmarks",
  kind: "list",
  dataKey: "benchmarkPages",
  hub: { href: "/benchmarks", label: "Overview" },
};

describe("MobileDrawerSectionContent", () => {
  it("renders all benchmark sub-pages in the mobile drawer", () => {
    render(
      <MobileDrawerSectionContent
        section={benchmarkSection}
        data={mobileNavData}
        pathname="/benchmarks"
        onClose={() => {}}
      />,
    );

    expect(screen.getAllByText("Overview")).toHaveLength(1);
    expect(screen.getByText("Latency")).toBeInTheDocument();
    expect(screen.getByText("Waterfall")).toBeInTheDocument();
    expect(screen.getByText("Load test")).toBeInTheDocument();
    expect(screen.getByText("History")).toBeInTheDocument();
    expect(screen.getByText("Compare")).toBeInTheDocument();
  });
});
