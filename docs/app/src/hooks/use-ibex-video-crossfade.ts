"use client";

import { useEffect, useRef, useState } from "react";

import { wireCrossfadePlayback } from "@/lib/ibex-video-crossfade-logic";

const POSTER_SRC = "/ibex-ascii-poster.webp";

export function useIbexVideoCrossfade() {
  const aRef = useRef<HTMLVideoElement>(null);
  const bRef = useRef<HTMLVideoElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<"a" | "b">("a");
  const staggeredRef = useRef(false);
  const [activeClass, setActiveClass] = useState<"a" | "b">("a");
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return undefined;
    const observer = new IntersectionObserver(
      ([entry]) => setInView(entry.isIntersecting),
      { threshold: 0.1 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const a = aRef.current;
    const b = bRef.current;
    if (!a || !b) return undefined;

    const reduceMotion = globalThis.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    if (!inView || reduceMotion) {
      a.pause();
      b.pause();
      return undefined;
    }

    return wireCrossfadePlayback(a, b, activeRef, setActiveClass, staggeredRef);
  }, [inView]);

  const videoClass = (isActive: boolean) =>
    [
      "video-blend animate-float absolute inset-0 h-full w-full object-contain",
      "transition-opacity duration-1000",
      isActive ? "opacity-100" : "opacity-0",
    ].join(" ");

  return {
    aRef,
    bRef,
    wrapRef,
    posterSrc: POSTER_SRC,
    videoClass,
    isAActive: activeClass === "a",
    isBActive: activeClass === "b",
  };
}
