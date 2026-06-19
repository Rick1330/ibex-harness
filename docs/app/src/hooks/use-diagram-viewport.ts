"use client";

import { useCallback, useEffect, useRef, useState, type PointerEvent } from "react";

import { useSingleDiagramViewport } from "@/hooks/use-single-diagram-viewport";

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
  const inline = useSingleDiagramViewport({ enabled: true });
  const modal = useSingleDiagramViewport({ enabled: isOpen });

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
