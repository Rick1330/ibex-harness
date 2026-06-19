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

function useDiagramFitHandlers(
  hostRef: RefObject<HTMLDivElement | null>,
  modalHostRef: RefObject<HTMLDivElement | null>,
  svg: string | null,
  fitInline: (source: SVGSVGElement | string | null) => void,
  fitModal: (source: SVGSVGElement | string | null) => void,
) {
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
  }, [fitModal, modalHostRef, svg]);

  return { runFitInline, runFitModal };
}

type DiagramInlinePanelProps = Readonly<{
  rootRef: RefObject<HTMLDivElement | null>;
  fullscreenButtonRef: RefObject<HTMLButtonElement | null>;
  inline: ReturnType<typeof useDiagramViewports>["inline"];
  rendering: boolean;
  svg: string | null;
  onCollapse?: () => void;
  onFit: () => void;
  onFullscreen: () => void;
  children: ReactNode;
}>;

function DiagramInlinePanel({
  rootRef,
  fullscreenButtonRef,
  inline,
  rendering,
  svg,
  onCollapse,
  onFit,
  onFullscreen,
  children,
}: DiagramInlinePanelProps) {
  return (
    <div
      ref={rootRef}
      className="relative my-6 w-full rounded-md border border-border bg-panel p-4"
    >
      <div className="absolute end-3 top-3 z-10">
        <DiagramToolbar
          fullscreenButtonRef={fullscreenButtonRef}
          fullscreenDisabled={rendering || !svg}
          onClose={onCollapse}
          onFit={onFit}
          onFullscreen={onFullscreen}
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
  );
}

export function DeepWikiStyleWrapper({
  children,
  svg,
  rendering = false,
  hostRef,
  onCollapse,
}: DeepWikiStyleWrapperProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const modalHostRef = useRef<HTMLDivElement>(null);
  const viewports = useDiagramViewports();
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

  const { runFitInline, runFitModal } = useDiagramFitHandlers(
    hostRef,
    modalHostRef,
    svg,
    fitInline,
    fitModal,
  );

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
      <DiagramInlinePanel
        fullscreenButtonRef={fullscreenButtonRef}
        inline={inline}
        onCollapse={onCollapse}
        onFit={runFitInline}
        onFullscreen={handleOpenModal}
        rendering={rendering}
        rootRef={rootRef}
        svg={svg}
      >
        {children}
      </DiagramInlinePanel>

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
