"use client";

import { useCallback, useRef, useState } from "react";

import type { DiagramPosition } from "@/lib/diagram-fit";

type PointerDragOptions = Readonly<{
  enabled: boolean;
  position: DiagramPosition;
  setPosition: (value: DiagramPosition) => void;
}>;

export function useDiagramPointerDrag({
  enabled,
  position,
  setPosition,
}: PointerDragOptions) {
  const [isDragging, setIsDragging] = useState(false);
  const dragStart = useRef<DiagramPosition>({ x: 0, y: 0 });

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
    [enabled, isDragging, setPosition],
  );

  const stopDragging = useCallback(() => {
    setIsDragging(false);
  }, []);

  return {
    handlePointerDown,
    handlePointerMove,
    isDragging,
    stopDragging,
  };
}
