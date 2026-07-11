"use client";

import { useEffect, useRef, useState } from "react";

/** Returns a ref and whether its element is intersecting the viewport. */
export function useInView<T extends HTMLElement>(threshold = 0.1) {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const observer = new IntersectionObserver(
      ([entry]) => {
        setInView(entry.isIntersecting);
      },
      { threshold },
    );
    observer.observe(el);
    return () => {
      observer.disconnect();
    };
  }, [threshold]);

  return { ref, inView } as const;
}
