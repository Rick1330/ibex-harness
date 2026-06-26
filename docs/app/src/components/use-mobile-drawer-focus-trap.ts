"use client";

import { useEffect } from "react";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input, textarea, select, [tabindex]:not([tabindex="-1"])';

function listFocusableElements(drawer: HTMLElement): HTMLElement[] {
  return Array.from(
    drawer.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  ).filter((el) => !el.hasAttribute("aria-hidden"));
}

function focusFirstElement(drawer: HTMLElement) {
  const focusable = listFocusableElements(drawer);
  if (focusable.length === 0) return;
  focusable[0].focus();
}

function trapTabBetweenEnds(
  event: KeyboardEvent,
  first: HTMLElement,
  last: HTMLElement,
) {
  if (event.shiftKey) {
    if (document.activeElement !== first) return;
    event.preventDefault();
    last.focus();
    return;
  }

  if (document.activeElement !== last) return;
  event.preventDefault();
  first.focus();
}

function restoreFocus(element: HTMLElement | null) {
  if (element && document.contains(element)) {
    element.focus();
  }
}

export function useMobileDrawerFocusTrap(open: boolean, drawerId: string) {
  useEffect(() => {
    if (!open) return;

    const drawer = document.getElementById(drawerId);
    if (!drawer) return;

    const previouslyFocused =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;

      const focusable = listFocusableElements(drawer);
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      trapTabBetweenEnds(event, first, last);
    };

    document.addEventListener("keydown", handleKeyDown);
    focusFirstElement(drawer);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      restoreFocus(previouslyFocused);
    };
  }, [drawerId, open]);
}
