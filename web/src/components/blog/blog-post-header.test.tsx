import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BlogPostHeader } from "@/components/blog/blog-post-header";

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

afterEach(() => {
  cleanup();
});

describe("BlogPostHeader", () => {
  it("links back to blog and author to GitHub", () => {
    const { container } = render(
      <BlogPostHeader
        title="Hello world"
        date="2026-07-16"
        category="Engineering"
        author="Rick1330"
        authorUrl="https://github.com/Rick1330"
        readingTime="5 min read"
      />,
    );

    expect(screen.getByRole("link", { name: /Back to blog/i })).toHaveAttribute(
      "href",
      "/blog",
    );
    const author = screen.getByRole("link", { name: /Rick1330/i });
    expect(author).toHaveAttribute("href", "https://github.com/Rick1330");
    expect(container.querySelector("svg")).not.toBeNull();
    expect(screen.getByText("Engineering")).toBeInTheDocument();
    expect(screen.getByText("RI")).toBeInTheDocument();
  });

  it("renders author as plain text when authorUrl is missing", () => {
    render(
      <BlogPostHeader
        title="Hello"
        date="2026-07-16"
        category="Product"
        author="Rick1330"
      />,
    );

    expect(screen.getByRole("link", { name: /Back to blog/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Rick1330/i })).toBeNull();
    expect(screen.getByText("Rick1330")).toBeInTheDocument();
  });
});
