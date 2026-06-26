import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useMobileDrawerFocusTrap } from "@/components/use-mobile-drawer-focus-trap";

function mountDrawer(id: string) {
  const drawer = document.createElement("nav");
  drawer.id = id;

  const first = document.createElement("button");
  first.textContent = "First";
  const last = document.createElement("button");
  last.textContent = "Last";

  drawer.append(first, last);
  document.body.append(drawer);

  return { drawer, first, last };
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("useMobileDrawerFocusTrap", () => {
  it("moves focus to the first focusable element on open", () => {
    const { first } = mountDrawer("trap-drawer");

    renderHook(() => useMobileDrawerFocusTrap(true, "trap-drawer"));

    expect(document.activeElement).toBe(first);
  });

  it("wraps focus from last to first on Tab", () => {
    const { first, last } = mountDrawer("trap-drawer");

    renderHook(() => useMobileDrawerFocusTrap(true, "trap-drawer"));
    last.focus();

    act(() => {
      document.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Tab", bubbles: true }),
      );
    });

    expect(document.activeElement).toBe(first);
  });

  it("restores focus to the previously focused element on close", () => {
    const trigger = document.createElement("button");
    trigger.textContent = "Menu";
    document.body.append(trigger);
    trigger.focus();

    mountDrawer("trap-drawer");

    const { unmount } = renderHook(() =>
      useMobileDrawerFocusTrap(true, "trap-drawer"),
    );
    unmount();

    expect(document.activeElement).toBe(trigger);
  });
});
