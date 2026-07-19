import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NavGithubLink } from "@/components/layout/nav-github-link";
import { GITHUB_OWNER, GITHUB_REPO } from "@/lib/github";

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

describe("NavGithubLink", () => {
  it("renders icon-only link to the repository", () => {
    const { container } = render(<NavGithubLink />);

    const link = screen.getByRole("link", { name: "GitHub repository" });
    expect(link).toHaveAttribute(
      "href",
      `https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}`,
    );
    expect(container.querySelector("svg")).not.toBeNull();
    expect(screen.queryByText("GitHub")).toBeNull();
  });

  it("renders a single labeled link with responsive label class", () => {
    render(<NavGithubLink showLabel />);

    const label = screen.getByText("GitHub");
    expect(label).toHaveClass("site-nav-github-label");
    expect(label).toHaveClass("hidden");
    expect(label).toHaveClass("sm:inline");
    expect(screen.getAllByRole("link", { name: "GitHub repository" })).toHaveLength(
      1,
    );
  });
});
