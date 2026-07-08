"use client";

import { useEffect, useRef, useState } from "react";

const POSTER_SRC = "/ibex-ascii-poster.webp";
const FADE_SECONDS = 0.6;

function playVideo(video: HTMLVideoElement) {
  video.play().catch(() => {
    /* Autoplay blocked or element detached — poster remains visible. */
  });
}

export function IbexVideo() {
  const aRef = useRef<HTMLVideoElement>(null);
  const bRef = useRef<HTMLVideoElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState<"a" | "b">("a");
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

    if (!inView) {
      a.pause();
      b.pause();
      return undefined;
    }

    if (reduceMotion) {
      a.currentTime = 0;
      b.pause();
      return undefined;
    }

    const onTime =
      (
        self: HTMLVideoElement,
        other: HTMLVideoElement,
        id: "a" | "b",
      ) =>
      () => {
        if (
          self.duration &&
          self.currentTime > self.duration - FADE_SECONDS &&
          active === id
        ) {
          other.currentTime = 0;
          playVideo(other);
          setActive(id === "a" ? "b" : "a");
        }
      };

    const onTimeA = onTime(a, b, "a");
    const onTimeB = onTime(b, a, "b");
    a.addEventListener("timeupdate", onTimeA);
    b.addEventListener("timeupdate", onTimeB);
    playVideo(active === "a" ? a : b);

    return () => {
      a.removeEventListener("timeupdate", onTimeA);
      b.removeEventListener("timeupdate", onTimeB);
    };
  }, [inView, active]);

  const videoClass = (isActive: boolean) =>
    [
      "video-blend animate-float absolute inset-0 h-full w-full object-contain",
      "transition-opacity duration-700",
      isActive ? "opacity-100" : "opacity-0",
    ].join(" ");

  return (
    <div
      ref={wrapRef}
      className="ibex-video-stage relative aspect-square w-[115%] max-w-none md:-ml-10 lg:w-[640px]"
      aria-hidden
    >
      <video
        ref={aRef}
        className={videoClass(active === "a")}
        poster={POSTER_SRC}
        muted
        playsInline
        preload="metadata"
        tabIndex={-1}
      >
        <source src="/ibex-ascii.webm" type="video/webm" />
        <source src="/ibex-ascii.mp4" type="video/mp4" />
      </video>
      <video
        ref={bRef}
        className={videoClass(active === "b")}
        muted
        playsInline
        preload="none"
        tabIndex={-1}
      >
        <source src="/ibex-ascii.webm" type="video/webm" />
        <source src="/ibex-ascii.mp4" type="video/mp4" />
      </video>
    </div>
  );
}
