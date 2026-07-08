export const FADE_SECONDS = 1.25;

export function playVideo(video: HTMLVideoElement) {
  if (video.paused) {
    void video.play().catch(() => {
      /* Autoplay blocked or element detached — poster remains visible. */
    });
  }
}

type TrackId = "a" | "b";

function armCrossfade(
  leader: HTMLVideoElement,
  follower: HTMLVideoElement,
  leaderId: TrackId,
  activeRef: { current: TrackId },
  swapTo: (next: TrackId) => void,
  armedRef: { current: boolean },
) {
  if (!leader.duration || activeRef.current !== leaderId || armedRef.current) {
    return;
  }

  const remaining = leader.duration - leader.currentTime;
  if (remaining > FADE_SECONDS + 0.15) {
    armedRef.current = false;
  }
  if (remaining > FADE_SECONDS) {
    return;
  }

  armedRef.current = true;
  follower.currentTime = 0;

  const beginFollower = () => {
    playVideo(follower);
    swapTo(leaderId === "a" ? "b" : "a");
  };

  if (follower.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
    beginFollower();
    return;
  }

  follower.addEventListener("canplay", beginFollower, { once: true });
}

function resetTrack(video: HTMLVideoElement) {
  video.pause();
  video.currentTime = 0;
}

export function wireCrossfadePlayback(
  a: HTMLVideoElement,
  b: HTMLVideoElement,
  activeRef: { current: TrackId },
  setActiveClass: (next: TrackId) => void,
) {
  const armedRef = { current: false };

  const swapTo = (next: TrackId) => {
    if (activeRef.current === next) return;
    activeRef.current = next;
    setActiveClass(next);
  };

  const onEndedA = () => {
    armedRef.current = false;
    if (activeRef.current === "a") return;
    resetTrack(a);
  };

  const onEndedB = () => {
    armedRef.current = false;
    if (activeRef.current === "b") return;
    resetTrack(b);
  };

  const tick = () => {
    if (activeRef.current === "a") {
      armCrossfade(a, b, "a", activeRef, swapTo, armedRef);
    } else {
      armCrossfade(b, a, "b", activeRef, swapTo, armedRef);
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
    window.cancelAnimationFrame(frameId);
    a.removeEventListener("loadedmetadata", onLoadedA);
    a.removeEventListener("ended", onEndedA);
    b.removeEventListener("ended", onEndedB);
    resetTrack(a);
    resetTrack(b);
  };
}
