"use client";

import { useEffect, useState } from "react";

import { useDiagramTheme } from "@/hooks/use-diagram-theme";
import { getStaticDiagramUrl } from "@/lib/diagram-static";

const STATIC_FETCH_TIMEOUT_MS = 8000;

type StaticDiagramOptions = Readonly<{
  enabled?: boolean;
}>;

type StaticDiagramState = Readonly<{
  svg: string | null;
  failed: boolean;
  loading: boolean;
}>;

export function useStaticDiagram(
  diagramKey: string,
  options: StaticDiagramOptions = {},
): StaticDiagramState {
  const { enabled = true } = options;
  const theme = useDiagramTheme();
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!enabled) {
      setSvg(null);
      setFailed(false);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => {
      controller.abort();
    }, STATIC_FETCH_TIMEOUT_MS);

    setSvg(null);
    setFailed(false);

    const url = getStaticDiagramUrl(diagramKey, theme);
    fetch(url, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("static diagram missing");
        return response.text();
      })
      .then((text) => {
        if (!cancelled) setSvg(text);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      })
      .finally(() => {
        window.clearTimeout(timeoutId);
      });

    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(timeoutId);
    };
  }, [diagramKey, enabled, theme]);

  return {
    svg,
    failed,
    loading: enabled && !svg && !failed,
  };
}
