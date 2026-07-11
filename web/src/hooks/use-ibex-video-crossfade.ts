"use client";

import { useEffect, useRef, useState } from "react";

import { useInView } from "@/hooks/use-in-view";
import {
  bindCrossfadePlayback,
  preloadForTrack,
  type TrackId,
  videoBlendClass,
} from "@/lib/ibex-video-crossfade-logic";
import type { IbexVideoSources } from "@/lib/ibex-video-sources";

const POSTER_SRC = "/ibex-ascii-poster.webp";

function setVideoSources(video: HTMLVideoElement, sources: IbexVideoSources) {
  const webm = video.querySelector('source[type="video/webm"]');
  const mp4 = video.querySelector('source[type="video/mp4"]');
  if (webm) webm.setAttribute("src", sources.webm);
  if (mp4) mp4.setAttribute("src", sources.mp4);
  video.load();
}

export function useIbexVideoCrossfade(sources: IbexVideoSources) {
  const aRef = useRef<HTMLVideoElement>(null);
  const bRef = useRef<HTMLVideoElement>(null);
  const { ref: wrapRef, inView } = useInView<HTMLDivElement>();
  const activeRef = useRef<TrackId>("a");
  const [activeClass, setActiveClass] = useState<TrackId>("a");

  useEffect(() => {
    const a = aRef.current;
    const b = bRef.current;
    if (!a || !b) return undefined;

    setVideoSources(a, sources);
    setVideoSources(b, sources);
    activeRef.current = "a";
    setActiveClass("a");

    return bindCrossfadePlayback(a, b, inView, activeRef, setActiveClass);
  }, [inView, sources.mp4, sources.webm]);

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
