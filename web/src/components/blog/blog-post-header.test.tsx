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
  it("links the author to GitHub and renders the Github icon", () => {
    const { container } = render(
      <BlogPostHeader
        title="Hello"
        date="2026-07-16"
        author="Rick1330"
        authorUrl="https://github.com/Rick1330"
      />,
    );

    const link = screen.getByRole("link", { name: /Rick1330/i });
    expect(link).toHaveAttribute("href", "https://github.com/Rick1330");
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("renders author as plain text when authorUrl is missing", () => {
    render(<BlogPostHeader title="Hello" date="2026-07-16" author="Rick1330" />);

    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("Rick1330")).toBeInTheDocument();
  });
});
