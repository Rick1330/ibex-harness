"use client";

import { useEffect, useRef, type ReactNode, type RefObject } from "react";

import { mountSvgString, normalizeMountedSvg } from "@/lib/mermaid-render";
import { cn } from "@/lib/cn";

type DiagramViewportSlice = Readonly<{
  canvasRef: RefObject<HTMLDivElement | null>;
  scale: number;
  position: Readonly<{ x: number; y: number }>;
  isDragging: boolean;
  handlePointerDown: (clientX: number, clientY: number) => void;
  handlePointerMove: (clientX: number, clientY: number) => void;
  stopDragging: () => void;
}>;

type DiagramCanvasProps = Readonly<{
  viewport: DiagramViewportSlice;
  className?: string;
  children?: ReactNode;
}>;

export function DiagramCanvas({
  viewport,
  className,
  children,
}: DiagramCanvasProps) {
  const {
    canvasRef,
    scale,
    position,
    isDragging,
    handlePointerDown,
    handlePointerMove,
    stopDragging,
  } = viewport;

  return (
    <div
      ref={canvasRef}
      className={cn("diagram-canvas relative overflow-hidden", className)}
      onPointerLeave={stopDragging}
      onPointerUp={stopDragging}
    >
      <div
        className={cn(
          "h-full w-full touch-none",
          isDragging ? "cursor-grabbing" : "cursor-grab",
        )}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          handlePointerDown(event.clientX, event.clientY);
        }}
        onPointerMove={(event) => {
          handlePointerMove(event.clientX, event.clientY);
        }}
      >
        <div
          className="inline-block min-h-[1px] min-w-[1px] origin-top-left"
          style={{
            transform: `translate(${position.x}px, ${position.y}px) scale(${scale})`,
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}

type DiagramCachedSvgProps = Readonly<{
  svg: string;
  hostRef?: RefObject<HTMLDivElement | null>;
  className?: string;
}>;

export function DiagramCachedSvg({
  svg,
  hostRef,
  className,
}: DiagramCachedSvgProps) {
  const localRef = useRef<HTMLDivElement>(null);
  const ref = hostRef ?? localRef;

  useEffect(() => {
    if (!ref.current) return;
    mountSvgString(ref.current, svg);
    normalizeMountedSvg(ref.current);
  }, [ref, svg]);

  return (
    <div
      ref={ref}
      className={cn(
        "diagram-cached-svg inline-block min-w-0 leading-none",
        className,
      )}
    />
  );
}
