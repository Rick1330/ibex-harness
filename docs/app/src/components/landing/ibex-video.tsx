"use client";

import { useIbexVideoCrossfade } from "@/hooks/use-ibex-video-crossfade";

export function IbexVideo() {
  const {
    aRef,
    bRef,
    wrapRef,
    posterSrc,
    videoClass,
    isAActive,
    isBActive,
  } = useIbexVideoCrossfade();

  return (
    <div
      ref={wrapRef}
      className="ibex-video-stage relative aspect-square w-[115%] max-w-none md:-ml-10 lg:w-[640px]"
      aria-hidden
    >
      <video
        ref={aRef}
        className={videoClass(isAActive)}
        poster={posterSrc}
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
        className={videoClass(isBActive)}
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
