"use client";

import { Maximize2 } from "lucide-react";
import { useCallback, useEffect, useRef } from "react";

import {
  DiagramFullscreenModal,
} from "@/components/mdx/diagram-fullscreen-modal";
import { useDiagramViewports } from "@/hooks/use-diagram-viewport";
import { cn } from "@/lib/cn";

type MermaidStaticShellProps = Readonly<{
  svg: string;
  className?: string;
}>;

export function MermaidStaticShell({ svg, className }: MermaidStaticShellProps) {
  const viewports = useDiagramViewports();
  const modalHostRef = useRef<HTMLDivElement>(null);
  const { fitModal, isOpen, openModal } = viewports;

  const runFitModal = useCallback(() => {
    fitModal(svg);
  }, [fitModal, svg]);

  useEffect(() => {
    if (!isOpen) return;
    runFitModal();
  }, [isOpen, runFitModal]);

  return (
    <>
      <div
        className={cn(
          "relative my-6 w-full rounded-xl border border-border bg-panel p-4",
          className,
        )}
      >
        <div className="absolute end-3 top-3 z-10">
          <button
            type="button"
            aria-label="Open fullscreen diagram viewer"
            className={cn(
              "inline-flex size-8 items-center justify-center rounded-md border border-border bg-panel/30 text-text-secondary transition-colors",
              "hover:bg-panel-raised hover:text-text-primary",
            )}
            onClick={openModal}
          >
            <Maximize2 className="size-4" strokeWidth={1.5} />
          </button>
        </div>
        <div
          className="diagram-static-svg overflow-x-auto rounded-[4px] border border-border/60 bg-panel p-4"
          data-diagram-static
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>

      <DiagramFullscreenModal
        modalHostRef={modalHostRef}
        onFit={runFitModal}
        svg={svg}
        viewports={viewports}
      />
    </>
  );
}
