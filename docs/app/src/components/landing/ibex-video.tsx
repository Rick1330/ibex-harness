"use client";

import { useEffect, useRef, useState } from "react";

const POSTER_SRC = "/ibex-ascii-poster.webp";

export function IbexVideo() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
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
    const video = videoRef.current;
    if (!video) return undefined;
    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    if (!inView || reduceMotion) {
      video.pause();
      return undefined;
    }

    void video.play();
    return () => {
      video.pause();
    };
  }, [inView]);

  return (
    <div
      ref={wrapRef}
      className="relative aspect-square w-[115%] max-w-none md:-ml-10 lg:w-[640px]"
    >
      <video
        ref={videoRef}
        className="video-blend animate-float absolute inset-0 h-full w-full object-contain"
        poster={POSTER_SRC}
        muted
        loop
        playsInline
        autoPlay
        preload="metadata"
        aria-hidden
      >
        <source src="/ibex-ascii.webm" type="video/webm" />
        <source src="/ibex-ascii.mp4" type="video/mp4" />
      </video>
    </div>
  );
}
