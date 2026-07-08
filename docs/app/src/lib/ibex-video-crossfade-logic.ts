export const FADE_SECONDS = 1.0;

export function playVideo(video: HTMLVideoElement) {
  video.play().catch(() => {
    /* Autoplay blocked or element detached — poster remains visible. */
  });
}

type TrackId = "a" | "b";

export function wireCrossfadePlayback(
  a: HTMLVideoElement,
  b: HTMLVideoElement,
  activeRef: { current: TrackId },
  setActiveClass: (next: TrackId) => void,
  staggeredRef: { current: boolean },
) {
  const swapTo = (next: TrackId) => {
    if (activeRef.current === next) return;
    activeRef.current = next;
    setActiveClass(next);
  };

  const prepareCrossfade = (
    self: HTMLVideoElement,
    other: HTMLVideoElement,
    id: TrackId,
  ) => {
    if (!self.duration || self.currentTime < self.duration - FADE_SECONDS) {
      return;
    }
    if (activeRef.current !== id) return;

    other.currentTime = 0;
    playVideo(other);
    swapTo(id === "a" ? "b" : "a");
  };

  const onEnded =
    (self: HTMLVideoElement, other: HTMLVideoElement, id: TrackId) => () => {
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
}
