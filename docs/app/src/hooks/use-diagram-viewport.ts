"use client";

import { useCallback, useEffect, useRef, useState, type PointerEvent } from "react";

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

function useSingleViewport({ enabled }: SingleViewportOptions) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState<DiagramPosition>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStart = useRef<DiagramPosition>({ x: 0, y: 0 });

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
    },
    [applyFitTransform],
  );

  const handlePointerDown = useCallback(
    (clientX: number, clientY: number) => {
      if (!enabled) return;
      setIsDragging(true);
      dragStart.current = {
        x: clientX - position.x,
        y: clientY - position.y,
      };
    },
    [enabled, position.x, position.y],
  );

  const handlePointerMove = useCallback(
    (clientX: number, clientY: number) => {
      if (!isDragging || !enabled) return;
      setPosition({
        x: clientX - dragStart.current.x,
        y: clientY - dragStart.current.y,
      });
    },
    [enabled, isDragging],
  );

  const stopDragging = useCallback(() => {
    setIsDragging(false);
  }, []);

  useEffect(() => {
    const element = canvasRef.current;
    if (!element || !enabled) return;

    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const delta = event.deltaY > 0 ? -WHEEL_ZOOM_STEP : WHEEL_ZOOM_STEP;
      setScale((current) => clampScale(current + delta));
    };

    element.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      element.removeEventListener("wheel", onWheel);
    };
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

type SvgSource = SVGSVGElement | string | null;

const FIT_RETRY_LIMIT = 12;

function scheduleFit(
  fit: (source: SvgSource) => boolean,
  svgSource: SvgSource,
) {
  let attempts = 0;
  const tryFit = () => {
    attempts += 1;
    if (fit(svgSource) || attempts >= FIT_RETRY_LIMIT) return;
    requestAnimationFrame(tryFit);
  };
  requestAnimationFrame(tryFit);
}

export function useDiagramViewports() {
  const [isOpen, setIsOpen] = useState(false);
  const fullscreenButtonRef = useRef<HTMLButtonElement>(null);
  const inline = useSingleViewport({ enabled: true });
  const modal = useSingleViewport({ enabled: isOpen });

  const openModal = useCallback(() => {
    setIsOpen(true);
  }, []);

  const stopModalDragging = modal.stopDragging;

  const closeModal = useCallback(() => {
    setIsOpen(false);
    stopModalDragging();
    fullscreenButtonRef.current?.focus();
  }, [stopModalDragging]);

  const onOverlayPointerDown = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      if (event.target === event.currentTarget) closeModal();
    },
    [closeModal],
  );

  useEffect(() => {
    if (!isOpen) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeModal();
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [closeModal, isOpen]);

  const fitInline = useCallback(
    (svgSource: SvgSource) => {
      scheduleFit(inline.fitToView, svgSource);
    },
    [inline.fitToView],
  );

  const fitModal = useCallback(
    (svgSource: SvgSource) => {
      if (!isOpen) return;
      scheduleFit(modal.fitToView, svgSource);
    },
    [isOpen, modal.fitToView],
  );

  return {
    closeModal,
    fitInline,
    fitModal,
    fullscreenButtonRef,
    inline,
    isOpen,
    modal,
    onOverlayPointerDown,
    openModal,
  };
}
