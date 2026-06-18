"use client";

import { useEffect, useState } from "react";

import { getDiagramChartUrl } from "@/lib/diagram-static";

type DiagramChartState = Readonly<{
  chart: string | null;
  loading: boolean;
  failed: boolean;
}>;

export function useDiagramChart(
  diagramKey: string,
  enabled: boolean,
): DiagramChartState {
  const [chart, setChart] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!enabled) {
      setChart(null);
      setFailed(false);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setChart(null);
    setFailed(false);
    setLoading(true);

    fetch(getDiagramChartUrl(diagramKey))
      .then((response) => {
        if (!response.ok) throw new Error("diagram source missing");
        return response.text();
      })
      .then((text) => {
        if (!cancelled) setChart(text.trim());
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [diagramKey, enabled]);

  return { chart, loading, failed };
}
