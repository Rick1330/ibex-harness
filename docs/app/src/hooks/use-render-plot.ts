"use client";

import { useEffect, type DependencyList, type RefObject } from "react";

type PlotModule = typeof import("@observablehq/plot");

let plotModulePromise: Promise<PlotModule> | undefined;

function loadPlotModule(): Promise<PlotModule> {
  plotModulePromise ??= import("@observablehq/plot");
  return plotModulePromise;
}

export function useRenderPlot(
  containerRef: RefObject<HTMLDivElement | null>,
  buildOptions: (width: number, Plot: PlotModule) => Parameters<PlotModule["plot"]>[0] | null,
  deps: DependencyList,
) {
  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    let cancelled = false;

    const render = () => {
      void loadPlotModule().then((Plot) => {
        if (cancelled) {
          return;
        }
        const width = container.clientWidth || 640;
        const options = buildOptions(width, Plot);
        if (!options) {
          return;
        }
        container.replaceChildren(Plot.plot(options));
      });
    };

    render();
    const observer = new ResizeObserver(render);
    observer.observe(container);

    return () => {
      cancelled = true;
      observer.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- caller supplies plot deps
  }, deps);
}
