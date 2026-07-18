import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CategoryFilter } from "@/components/blog/category-filter";

afterEach(() => {
  cleanup();
});

describe("CategoryFilter", () => {
  it("marks All as pressed when active is null", () => {
    render(<CategoryFilter active={null} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("selects a category and deselects via All", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <CategoryFilter active={null} onChange={onChange} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Engineering" }));
    expect(onChange).toHaveBeenCalledWith("Engineering");

    rerender(<CategoryFilter active="Engineering" onChange={onChange} />);
    expect(
      screen.getByRole("button", { name: "Engineering" }),
    ).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("button", { name: "All" }));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("toggles the active category off when clicked again", () => {
    const onChange = vi.fn();
    render(<CategoryFilter active="Product" onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: "Product" }));
    expect(onChange).toHaveBeenCalledWith(null);
  });
});
