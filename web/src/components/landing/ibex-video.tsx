"use client";

import { useTheme } from "next-themes";
import { useEffect, useMemo, useState } from "react";

import { useIbexVideoCrossfade } from "@/hooks/use-ibex-video-crossfade";
import {
  IBEX_VIDEO_POSTER,
  ibexVideoSourcesForTheme,
  type IbexVideoTheme,
} from "@/lib/ibex-video-sources";

function resolveVideoTheme(resolvedTheme: string | undefined): IbexVideoTheme {
  return resolvedTheme === "dark" ? "dark" : "light";
}

export function IbexVideo() {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const videoTheme = mounted ? resolveVideoTheme(resolvedTheme) : "light";
  const sources = useMemo(
    () => ibexVideoSourcesForTheme(videoTheme),
    [videoTheme],
  );

  const {
    aRef,
    bRef,
    wrapRef,
    videoClass,
    isAActive,
    isBActive,
    aPreload,
    bPreload,
  } = useIbexVideoCrossfade(sources);

  return (
    <div
      ref={wrapRef}
      className="ibex-video-stage animate-float relative aspect-square w-[115%] max-w-none md:-ml-10 lg:w-[640px]"
      aria-hidden
    >
      <video
        ref={aRef}
        className={videoClass(isAActive)}
        poster={IBEX_VIDEO_POSTER}
        muted
        playsInline
        preload={aPreload}
        tabIndex={-1}
      >
        <source src={sources.webm} type="video/webm" />
        <source src={sources.mp4} type="video/mp4" />
      </video>
      <video
        ref={bRef}
        className={videoClass(isBActive)}
        muted
        playsInline
        preload={bPreload}
        tabIndex={-1}
      >
        <source src={sources.webm} type="video/webm" />
        <source src={sources.mp4} type="video/mp4" />
      </video>
    </div>
  );
}
