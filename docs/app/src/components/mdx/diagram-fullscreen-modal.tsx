"use client";

import {
  Maximize2,
  Minimize2,
  Minus,
  Plus,
  RotateCcw,
} from "lucide-react";
import { createPortal } from "react-dom";
import type { ReactNode, RefObject } from "react";

import {
  DiagramCachedSvg,
  DiagramCanvas,
} from "@/components/mdx/diagram-canvas";
import type { useDiagramViewports } from "@/hooks/use-diagram-viewport";
import { cn } from "@/lib/cn";

type ViewportState = ReturnType<typeof useDiagramViewports>;

type ToolbarButtonProps = Readonly<{
  label: string;
  onClick: () => void;
  children: ReactNode;
  disabled?: boolean;
  className?: string;
  buttonRef?: RefObject<HTMLButtonElement | null>;
}>;

function ToolbarButton({
  label,
  onClick,
  children,
  disabled,
  className,
  buttonRef,
}: ToolbarButtonProps) {
  return (
    <button
      ref={buttonRef}
      type="button"
      aria-label={label}
      disabled={disabled}
      className={cn(
        "inline-flex size-8 items-center justify-center rounded-md border border-border bg-panel/30 text-text-secondary transition-colors",
        "hover:bg-panel-raised hover:text-text-primary disabled:pointer-events-none disabled:opacity-40",
        className,
      )}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

type DiagramToolbarProps = Readonly<{
  onZoomOut: () => void;
  onZoomIn: () => void;
  onFit: () => void;
  onFullscreen?: () => void;
  onClose?: () => void;
  fullscreenDisabled?: boolean;
  fullscreenButtonRef?: RefObject<HTMLButtonElement | null>;
  showFullscreen?: boolean;
  showClose?: boolean;
}>;

export function DiagramToolbar({
  onZoomOut,
  onZoomIn,
  onFit,
  onFullscreen,
  onClose,
  fullscreenDisabled,
  fullscreenButtonRef,
  showFullscreen = false,
  showClose = false,
}: DiagramToolbarProps) {
  return (
    <div className="flex items-center gap-1">
      <ToolbarButton label="Zoom out" onClick={onZoomOut}>
        <Minus className="size-4" strokeWidth={1.5} />
      </ToolbarButton>
      <ToolbarButton label="Zoom in" onClick={onZoomIn}>
        <Plus className="size-4" strokeWidth={1.5} />
      </ToolbarButton>
      <ToolbarButton label="Fit to view" onClick={onFit}>
        <RotateCcw className="size-4" strokeWidth={1.5} />
      </ToolbarButton>
      {showFullscreen ? (
        <ToolbarButton
          buttonRef={fullscreenButtonRef}
          disabled={fullscreenDisabled}
          label="Open fullscreen"
          onClick={onFullscreen ?? (() => undefined)}
        >
          <Maximize2 className="size-4" strokeWidth={1.5} />
        </ToolbarButton>
      ) : null}
      {showClose ? (
        <>
          <div aria-hidden className="mx-1 h-4 w-px bg-border" />
          <ToolbarButton
            className="hover:bg-danger/10 hover:text-danger"
            label="Close diagram viewer"
            onClick={onClose ?? (() => undefined)}
          >
            <Minimize2 className="size-4" strokeWidth={1.5} />
          </ToolbarButton>
        </>
      ) : null}
    </div>
  );
}

type DiagramFullscreenModalProps = Readonly<{
  svg: string;
  viewports: ViewportState;
  modalHostRef: RefObject<HTMLDivElement | null>;
  onFit: () => void;
}>;

export function DiagramFullscreenModal({
  svg,
  viewports,
  modalHostRef,
  onFit,
}: DiagramFullscreenModalProps) {
  const { closeModal, isOpen, modal, onOverlayPointerDown } = viewports;

  if (!isOpen || typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex select-none items-center justify-center bg-black/50 p-6 backdrop-blur-md dark:bg-black/60"
      role="dialog"
      aria-modal="true"
      onPointerDown={onOverlayPointerDown}
    >
      <div
        className="relative flex h-full max-h-[85vh] w-full max-w-7xl flex-col overflow-hidden rounded-2xl border border-border bg-canvas p-6 shadow-2xl"
        onPointerDown={(event) => {
          event.stopPropagation();
        }}
      >
        <div className="absolute end-4 top-4 z-20">
          <DiagramToolbar
            onClose={closeModal}
            onFit={onFit}
            onZoomIn={modal.zoomIn}
            onZoomOut={modal.zoomOut}
            showClose
          />
        </div>

        <DiagramCanvas className="h-full min-h-0 flex-1" viewport={modal}>
          <DiagramCachedSvg hostRef={modalHostRef} svg={svg} />
        </DiagramCanvas>
      </div>
    </div>,
    document.body,
  );
}
