"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useDiagramPointerDrag } from "@/hooks/use-diagram-pointer-drag";
import {
  DIAGRAM_FIT_MIN_SCALE,
  DIAGRAM_MAX_SCALE,
  DIAGRAM_MIN_SCALE,
  fitTransformForContainer,
  type DiagramPosition,
} from "@/lib/diagram-fit";

const BUTTON_ZOOM_STEP = 0.1;
const WHEEL_ZOOM_STEP = 0.05;

type SingleViewportOptions = Readonly<{
  enabled: boolean;
}>;

function clampScale(value: number): number {
  return Math.min(DIAGRAM_MAX_SCALE, Math.max(DIAGRAM_MIN_SCALE, value));
}

function attachWheelZoom(
  element: HTMLDivElement,
  setScale: (updater: (current: number) => number) => void,
) {
  const onWheel = (event: WheelEvent) => {
    event.preventDefault();
    const delta = event.deltaY > 0 ? -WHEEL_ZOOM_STEP : WHEEL_ZOOM_STEP;
    setScale((current) => clampScale(current + delta));
  };

  element.addEventListener("wheel", onWheel, { passive: false });
  return () => {
    element.removeEventListener("wheel", onWheel);
  };
}

function fitSvgInContainer(
  container: HTMLDivElement,
  svgSource: SVGSVGElement | string,
  applyFitTransform: (scale: number, position: DiagramPosition) => void,
) {
  if (container.clientWidth <= 0 || container.clientHeight <= 0) {
    return false;
  }
  const transform = fitTransformForContainer(
    svgSource,
    container.clientWidth,
    container.clientHeight,
  );
  if (!transform) return false;
  applyFitTransform(transform.scale, transform.position);
  return true;
}

export function useSingleDiagramViewport({ enabled }: SingleViewportOptions) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState<DiagramPosition>({ x: 0, y: 0 });

  const zoomIn = useCallback(() => {
    setScale((current) => clampScale(current + BUTTON_ZOOM_STEP));
  }, []);

  const zoomOut = useCallback(() => {
    setScale((current) => clampScale(current - BUTTON_ZOOM_STEP));
  }, []);

  const applyFitTransform = useCallback(
    (nextScale: number, nextPosition: DiagramPosition) => {
      setScale(
        Math.min(DIAGRAM_MAX_SCALE, Math.max(DIAGRAM_FIT_MIN_SCALE, nextScale)),
      );
      setPosition(nextPosition);
    },
    [],
  );

  const fitToView = useCallback(
    (svgSource: SVGSVGElement | string | null) => {
      const container = canvasRef.current;
      if (!container || !svgSource) return false;
      return fitSvgInContainer(container, svgSource, applyFitTransform);
    },
    [applyFitTransform],
  );

  const {
    handlePointerDown,
    handlePointerMove,
    isDragging,
    stopDragging,
  } = useDiagramPointerDrag({ enabled, position, setPosition });

  useEffect(() => {
    const element = canvasRef.current;
    if (!element || !enabled) return;
    return attachWheelZoom(element, setScale);
  }, [enabled]);

  return {
    canvasRef,
    fitToView,
    handlePointerDown,
    handlePointerMove,
    isDragging,
    position,
    scale,
    stopDragging,
    zoomIn,
    zoomOut,
  };
}
