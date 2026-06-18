"use client";

import { useSyncExternalStore } from "react";
import { useTheme } from "next-themes";

import type { DiagramTheme } from "@/lib/diagram-static";

function getDomTheme(): DiagramTheme {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

function subscribeDomTheme(callback: () => void): () => void {
  const observer = new MutationObserver(callback);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class"],
  });
  return () => observer.disconnect();
}

/** Resolve diagram theme from next-themes, falling back to the html class. */
export function useDiagramTheme(): DiagramTheme {
  const { resolvedTheme } = useTheme();
  const domTheme = useSyncExternalStore(
    subscribeDomTheme,
    getDomTheme,
    (): DiagramTheme => "dark",
  );

  if (resolvedTheme === "light" || resolvedTheme === "dark") {
    return resolvedTheme as DiagramTheme;
  }
  return domTheme;
}
