"use client";

import {
  useCallback,
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
import { useDiagramAutoFit } from "@/hooks/use-diagram-auto-fit";
import { useDiagramViewports } from "@/hooks/use-diagram-viewport";
import { normalizeMountedSvg } from "@/lib/mermaid-render";

type DeepWikiStyleWrapperProps = Readonly<{
  children: ReactNode;
  svg: string | null;
  rendering?: boolean;
  hostRef: RefObject<HTMLDivElement | null>;
  onCollapse?: () => void;
}>;

function resolveSvgFromHost(
  host: HTMLDivElement | null,
): SVGSVGElement | null {
  if (!host) return null;
  return normalizeMountedSvg(host) ?? host.querySelector("svg");
}

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

  const runFitInline = useCallback(() => {
    const svgEl = resolveSvgFromHost(hostRef.current);
    if (svgEl) {
      fitInline(svgEl);
      return;
    }
    if (svg) fitInline(svg);
  }, [fitInline, hostRef, svg]);

  const runFitModal = useCallback(() => {
    const svgEl = resolveSvgFromHost(modalHostRef.current);
    if (svgEl) {
      fitModal(svgEl);
      return;
    }
    if (svg) fitModal(svg);
  }, [fitModal, svg]);

  useDiagramAutoFit({
    enabled: Boolean(svg) && !rendering,
    onFit: runFitInline,
  });

  useDiagramAutoFit({
    enabled: isOpen && Boolean(svg),
    onFit: runFitModal,
  });

  const handleOpenModal = useCallback(() => {
    if (!svg || rendering) return;
    openModal();
  }, [openModal, rendering, svg]);

  return (
    <>
      <div
        ref={rootRef}
        className="relative my-6 w-full rounded-md border border-border bg-panel p-4"
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
