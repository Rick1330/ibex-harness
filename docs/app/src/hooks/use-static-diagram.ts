"use client";

import { useEffect, useState } from "react";

import { useDiagramTheme } from "@/hooks/use-diagram-theme";
import { getStaticDiagramUrl } from "@/lib/diagram-static";

type StaticDiagramState = Readonly<{
  svg: string | null;
  failed: boolean;
  loading: boolean;
}>;

export function useStaticDiagram(diagramKey: string): StaticDiagramState {
  const theme = useDiagramTheme();
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setSvg(null);
    setFailed(false);

    const url = getStaticDiagramUrl(diagramKey, theme);
    fetch(url)
      .then((response) => {
        if (!response.ok) throw new Error("static diagram missing");
        return response.text();
      })
      .then((text) => {
        if (!cancelled) setSvg(text);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });

    return () => {
      cancelled = true;
    };
  }, [diagramKey, theme]);

  return {
    svg,
    failed,
    loading: !svg && !failed,
  };
}
