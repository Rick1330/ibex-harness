"use client";

import { useEffect, useRef, useState } from "react";

const POSTER_SRC = "/ibex-ascii-poster.webp";
const FADE_SECONDS = 1.0;

function playVideo(video: HTMLVideoElement) {
  video.play().catch(() => {
    /* Autoplay blocked or element detached — poster remains visible. */
  });
}

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

    const swapTo = (next: "a" | "b") => {
      if (activeRef.current === next) return;
      activeRef.current = next;
      setActiveClass(next);
    };

    const prepareCrossfade = (
      self: HTMLVideoElement,
      other: HTMLVideoElement,
      id: "a" | "b",
    ) => {
      if (!self.duration || self.currentTime < self.duration - FADE_SECONDS) {
        return;
      }
      if (activeRef.current !== id) return;

      other.currentTime = 0;
      playVideo(other);
      swapTo(id === "a" ? "b" : "a");
    };

    const onEnded = (self: HTMLVideoElement, other: HTMLVideoElement, id: "a" | "b") => () => {
      if (activeRef.current !== id) return;
      other.currentTime = 0;
      playVideo(other);
      swapTo(id === "a" ? "b" : "a");
    };

    const onTimeA = () => prepareCrossfade(a, b, "a");
    const onTimeB = () => prepareCrossfade(b, a, "b");
    const onEndedA = onEnded(a, b, "a");
    const onEndedB = onEnded(b, a, "b");

    const startPlayback = () => {
      if (!staggeredRef.current && a.duration) {
        b.currentTime = a.duration / 2;
        staggeredRef.current = true;
      }
      playVideo(activeRef.current === "a" ? a : b);
    };

    if (a.readyState >= 1) {
      startPlayback();
    } else {
      a.addEventListener("loadedmetadata", startPlayback, { once: true });
    }

    a.addEventListener("timeupdate", onTimeA);
    b.addEventListener("timeupdate", onTimeB);
    a.addEventListener("ended", onEndedA);
    b.addEventListener("ended", onEndedB);

    return () => {
      a.removeEventListener("timeupdate", onTimeA);
      b.removeEventListener("timeupdate", onTimeB);
      a.removeEventListener("ended", onEndedA);
      b.removeEventListener("ended", onEndedB);
      a.removeEventListener("loadedmetadata", startPlayback);
    };
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
