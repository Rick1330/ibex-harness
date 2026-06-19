"use client";

import { useEffect } from "react";

type AutoFitOptions = Readonly<{
  enabled: boolean;
  onFit: () => void;
}>;

/** Schedule a single fit pass after mount or when dependencies change. */
export function useDiagramAutoFit({ enabled, onFit }: AutoFitOptions) {
  useEffect(() => {
    if (!enabled) return;
    const timer = window.setTimeout(onFit, 0);
    return () => {
      window.clearTimeout(timer);
    };
  }, [enabled, onFit]);
}
