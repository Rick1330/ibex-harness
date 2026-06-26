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
  const initial = listFocusableElements(drawer)[0];
  if (initial) {
    initial.focus();
  }
}

function handleDrawerTabKey(event: KeyboardEvent, drawer: HTMLElement) {
  if (event.key !== "Tab") return;

  const focusable = listFocusableElements(drawer);
  if (focusable.length === 0) return;

  const first = focusable[0];
  const last = focusable.at(-1);
  if (!last) return;

  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
    return;
  }

  if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
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
      handleDrawerTabKey(event, drawer);
    };

    document.addEventListener("keydown", handleKeyDown);
    focusFirstElement(drawer);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      if (previouslyFocused && document.contains(previouslyFocused)) {
        previouslyFocused.focus();
      }
    };
  }, [drawerId, open]);
}
