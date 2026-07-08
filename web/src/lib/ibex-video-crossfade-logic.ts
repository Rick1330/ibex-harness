/** Use full media duration for loop timing. */
export const FADE_SECONDS = 1.5;

export type TrackId = "a" | "b";

export type CrossfadeOptions = {
  loopEndSeconds?: number;
  fadeSeconds?: number;
};

type CrossfadeCtx = {
  activeRef: { current: TrackId };
  armedRef: { current: boolean };
  swapTo: (next: TrackId) => void;
  loopEndSeconds?: number;
  fadeSeconds: number;
};

export function playVideo(video: HTMLVideoElement) {
  if (video.paused) {
    void video.play().catch(() => {
      /* Autoplay blocked or element detached — poster remains visible. */
    });
  }
}

export function loopEndSeconds(
  video: HTMLVideoElement,
  endSeconds?: number,
): number {
  if (!video.duration || !Number.isFinite(video.duration)) {
    return 0;
  }
  if (!endSeconds || !Number.isFinite(endSeconds)) {
    return video.duration;
  }
  return Math.min(endSeconds, video.duration);
}

export function secondsUntilLoopEnd(
  video: HTMLVideoElement,
  endSeconds?: number,
): number {
  const end = loopEndSeconds(video, endSeconds);
  if (end <= 0) {
    return Number.POSITIVE_INFINITY;
  }
  return end - video.currentTime;
}

function beginFollowerPlayback(
  follower: HTMLVideoElement,
  leaderId: TrackId,
  ctx: CrossfadeCtx,
) {
  playVideo(follower);
  ctx.swapTo(leaderId === "a" ? "b" : "a");
}

function armCrossfade(
  leader: HTMLVideoElement,
  follower: HTMLVideoElement,
  leaderId: TrackId,
  ctx: CrossfadeCtx,
) {
  if (ctx.armedRef.current) {
    return;
  }
  if (ctx.activeRef.current !== leaderId) {
    return;
  }

  const remaining = secondsUntilLoopEnd(leader, ctx.loopEndSeconds);
  if (!Number.isFinite(remaining)) {
    return;
  }

  if (remaining > ctx.fadeSeconds + 0.15) {
    ctx.armedRef.current = false;
  }
  if (remaining > ctx.fadeSeconds) {
    return;
  }

  ctx.armedRef.current = true;
  follower.currentTime = 0;

  if (follower.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
    beginFollowerPlayback(follower, leaderId, ctx);
    return;
  }

  follower.addEventListener(
    "canplay",
    () => beginFollowerPlayback(follower, leaderId, ctx),
    { once: true },
  );
}

function resetTrack(video: HTMLVideoElement) {
  video.pause();
  video.currentTime = 0;
}

function clampPastSegmentEnd(
  video: HTMLVideoElement,
  loopEnd: number,
  isActive: boolean,
) {
  if (loopEnd <= 0 || video.currentTime < loopEnd) {
    return;
  }
  if (isActive) {
    video.currentTime = 0;
    return;
  }
  resetTrack(video);
}

export function wireCrossfadePlayback(
  a: HTMLVideoElement,
  b: HTMLVideoElement,
  activeRef: { current: TrackId },
  setActiveClass: (next: TrackId) => void,
  options: CrossfadeOptions = {},
) {
  const loopEndSecondsOpt = options.loopEndSeconds;
  const fadeSeconds = options.fadeSeconds ?? FADE_SECONDS;
  const armedRef = { current: false };

  const swapTo = (next: TrackId) => {
    if (activeRef.current === next) {
      return;
    }
    const previous = activeRef.current;
    activeRef.current = next;
    setActiveClass(next);
    armedRef.current = false;
    const inactive = previous === "a" ? a : b;
    resetTrack(inactive);
  };

  const ctx: CrossfadeCtx = {
    activeRef,
    armedRef,
    swapTo,
    loopEndSeconds: loopEndSecondsOpt,
    fadeSeconds,
  };

  const onEndedA = () => {
    armedRef.current = false;
    if (activeRef.current === "a") {
      return;
    }
    resetTrack(a);
  };

  const onEndedB = () => {
    armedRef.current = false;
    if (activeRef.current === "b") {
      return;
    }
    resetTrack(b);
  };

  const tick = () => {
    const loopEnd = loopEndSeconds(a, loopEndSecondsOpt);
    if (activeRef.current === "a") {
      armCrossfade(a, b, "a", ctx);
      clampPastSegmentEnd(a, loopEnd, true);
      clampPastSegmentEnd(b, loopEnd, false);
    } else {
      armCrossfade(b, a, "b", ctx);
      clampPastSegmentEnd(b, loopEnd, true);
      clampPastSegmentEnd(a, loopEnd, false);
    }
    frameId = globalThis.requestAnimationFrame(tick);
  };

  let frameId = 0;

  const primeBoth = () => {
    a.loop = false;
    b.loop = false;
    playVideo(a);
    armedRef.current = false;
    activeRef.current = "a";
    setActiveClass("a");
    frameId = globalThis.requestAnimationFrame(tick);
  };

  const onLoadedA = () => {
    if (a.readyState >= HTMLMediaElement.HAVE_METADATA) {
      primeBoth();
    }
  };

  if (a.readyState >= HTMLMediaElement.HAVE_METADATA) {
    primeBoth();
  } else {
    a.addEventListener("loadedmetadata", onLoadedA, { once: true });
  }

  a.addEventListener("ended", onEndedA);
  b.addEventListener("ended", onEndedB);

  return () => {
    globalThis.cancelAnimationFrame(frameId);
    a.removeEventListener("loadedmetadata", onLoadedA);
    a.removeEventListener("ended", onEndedA);
    b.removeEventListener("ended", onEndedB);
    resetTrack(a);
    resetTrack(b);
  };
}
