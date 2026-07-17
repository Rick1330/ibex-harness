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

  it("renders the GitHub label when showLabel is set", () => {
    render(<NavGithubLink showLabel />);

    expect(screen.getByText("GitHub")).toBeInTheDocument();
  });
});
