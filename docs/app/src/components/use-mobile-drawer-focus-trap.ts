"use client";

import { useEffect } from "react";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input, textarea, select, [tabindex]:not([tabindex="-1"])';

function listFocusableElements(drawer: HTMLElement): HTMLElement[] {
  return Array.from(
    drawer.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  ).filter((el) => !el.hasAttribute("aria-hidden"));
}

function handleDrawerTabKey(event: KeyboardEvent, drawer: HTMLElement) {
  if (event.key !== "Tab") return;

  const focusable = listFocusableElements(drawer);
  if (focusable.length === 0) return;

  const first = focusable[0];
  const last = focusable[focusable.length - 1];

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

    const handleKeyDown = (event: KeyboardEvent) => {
      handleDrawerTabKey(event, drawer);
    };

    document.addEventListener("keydown", handleKeyDown);
    listFocusableElements(drawer)[0]?.focus();

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [drawerId, open]);
}
