"use client";

import { useEffect, useRef, useState } from "react";

import { useInView } from "@/hooks/use-in-view";
import {
  bindCrossfadePlayback,
  preloadForTrack,
  type TrackId,
  videoBlendClass,
} from "@/lib/ibex-video-crossfade-logic";

const POSTER_SRC = "/ibex-ascii-poster.webp";

export function useIbexVideoCrossfade() {
  const aRef = useRef<HTMLVideoElement>(null);
  const bRef = useRef<HTMLVideoElement>(null);
  const { ref: wrapRef, inView } = useInView<HTMLDivElement>();
  const activeRef = useRef<TrackId>("a");
  const [activeClass, setActiveClass] = useState<TrackId>("a");

  useEffect(() => {
    const a = aRef.current;
    const b = bRef.current;
    if (!a || !b) return undefined;
    return bindCrossfadePlayback(a, b, inView, activeRef, setActiveClass);
  }, [inView]);

  return {
    aRef,
    bRef,
    wrapRef,
    posterSrc: POSTER_SRC,
    videoClass: videoBlendClass,
    isAActive: activeClass === "a",
    isBActive: activeClass === "b",
    aPreload: preloadForTrack(activeClass, "a"),
    bPreload: preloadForTrack(activeClass, "b"),
  } as const;
}
