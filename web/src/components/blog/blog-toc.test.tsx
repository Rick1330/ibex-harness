import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BlogToc } from "@/components/blog/blog-toc";
import { TocScope } from "@/components/layout/toc-scope";

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: Readonly<{
    children: React.ReactNode;
    href: string;
  }>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

beforeEach(() => {
  class MockIntersectionObserver {
    observe = vi.fn();
    unobserve = vi.fn();
    disconnect = vi.fn();
  }
  vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
});

afterEach(() => {
  cleanup();
});

describe("BlogToc", () => {
  it("renders On this page header and heading links", () => {
    const items = [
      { title: "Two corpora, one product", url: "#two-corpora", depth: 2 },
      { title: "Docs site architecture", url: "#architecture", depth: 2 },
    ];

    render(
      <TocScope items={items}>
        <BlogToc items={items} />
      </TocScope>,
    );

    expect(
      screen.getByRole("navigation", { name: /On this page/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("On this page")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Two corpora/i })).toHaveAttribute(
      "href",
      "#two-corpora",
    );
    expect(
      screen.getByRole("link", { name: /Docs site architecture/i }),
    ).toHaveAttribute("href", "#architecture");
  });
});
