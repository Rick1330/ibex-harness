"use client";

import {
  useCallback,
  useEffect,
  useRef,
  type ReactNode,
  type RefObject,
} from "react";

import {
  DiagramFullscreenModal,
  DiagramToolbar,
} from "@/components/mdx/diagram-fullscreen-modal";
import { DiagramCanvas } from "@/components/mdx/diagram-canvas";
import { useClickOutside } from "@/hooks/use-click-outside";
import { useDiagramViewports } from "@/hooks/use-diagram-viewport";
import { normalizeMountedSvg } from "@/lib/mermaid-render";

type DeepWikiStyleWrapperProps = Readonly<{
  children: ReactNode;
  svg: string | null;
  rendering?: boolean;
  hostRef: RefObject<HTMLDivElement | null>;
  onCollapse?: () => void;
}>;

export function DeepWikiStyleWrapper({
  children,
  svg,
  rendering = false,
  hostRef,
  onCollapse,
}: DeepWikiStyleWrapperProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const viewports = useDiagramViewports();
  const modalHostRef = useRef<HTMLDivElement>(null);
  const {
    fitInline,
    fitModal,
    fullscreenButtonRef,
    inline,
    isOpen,
    openModal,
  } = viewports;

  useClickOutside(rootRef, Boolean(onCollapse) && !isOpen, () => {
    onCollapse?.();
  });

  const resolveInlineSvg = useCallback(() => {
    const host = hostRef.current;
    if (!host) return null;
    return normalizeMountedSvg(host) ?? host.querySelector("svg");
  }, [hostRef]);

  const runFitInline = useCallback(() => {
    const svgEl = resolveInlineSvg();
    if (svgEl) {
      fitInline(svgEl);
      return;
    }
    if (svg) fitInline(svg);
  }, [fitInline, resolveInlineSvg, svg]);

  const runFitModal = useCallback(() => {
    const host = modalHostRef.current;
    const svgEl = host ? normalizeMountedSvg(host) ?? host.querySelector("svg") : null;
    if (svgEl) {
      fitModal(svgEl);
      return;
    }
    if (svg) fitModal(svg);
  }, [fitModal, svg]);

  useEffect(() => {
    if (!svg || rendering) return;
    const timer = window.setTimeout(() => {
      runFitInline();
    }, 0);
    return () => {
      window.clearTimeout(timer);
    };
  }, [rendering, runFitInline, svg]);

  useEffect(() => {
    if (!isOpen || !svg) return;
    runFitModal();
  }, [isOpen, runFitModal, svg]);

  const handleOpenModal = useCallback(() => {
    if (!svg || rendering) return;
    openModal();
  }, [openModal, rendering, svg]);

  return (
    <>
      <div
        ref={rootRef}
        className="relative my-6 w-full rounded-xl border border-border bg-panel p-4"
      >
        <div className="absolute end-3 top-3 z-10">
          <DiagramToolbar
            fullscreenButtonRef={fullscreenButtonRef}
            fullscreenDisabled={rendering || !svg}
            onClose={onCollapse}
            onFit={runFitInline}
            onFullscreen={handleOpenModal}
            onZoomIn={inline.zoomIn}
            onZoomOut={inline.zoomOut}
            showClose={Boolean(onCollapse)}
            showFullscreen
          />
        </div>

        <DiagramCanvas className="h-[420px] w-full" viewport={inline}>
          {children}
        </DiagramCanvas>
      </div>

      {svg ? (
        <DiagramFullscreenModal
          modalHostRef={modalHostRef}
          onFit={runFitModal}
          svg={svg}
          viewports={viewports}
        />
      ) : null}
    </>
  );
}

/** @deprecated Use DeepWikiStyleWrapper — kept for existing imports. */
export const InteractiveMermaid = DeepWikiStyleWrapper;
