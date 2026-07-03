"use client";

import { useEffect } from "react";

import { BENCHMARK_DATA_URL } from "@/lib/benchmarks/constants";

function prefetchBenchmarkData() {
  void fetch(BENCHMARK_DATA_URL).catch(() => {
    // Best-effort warm cache; asset may be absent in local dev.
  });
}

/** Warm benchmark JSON on idle and when the user hovers a /benchmarks link. */
export function BenchmarkDataPrefetch() {
  useEffect(() => {
    if (!document.querySelector('a[href^="/benchmarks"]')) {
      return undefined;
    }

    let idleCallbackId: number | undefined;
    let timeoutId: ReturnType<typeof globalThis.setTimeout> | undefined;

    if (typeof globalThis.requestIdleCallback === "function") {
      idleCallbackId = globalThis.requestIdleCallback(() => { prefetchBenchmarkData(); });
    } else {
      timeoutId = globalThis.setTimeout(prefetchBenchmarkData, 2_000);
    }

    const onPointerOver = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }
      const link = target.closest('a[href^="/benchmarks"]');
      if (link) {
        prefetchBenchmarkData();
      }
    };

    document.addEventListener("pointerover", onPointerOver, { passive: true });

    return () => {
      document.removeEventListener("pointerover", onPointerOver);
      if (idleCallbackId !== undefined) {
        globalThis.cancelIdleCallback(idleCallbackId);
      }
      if (timeoutId !== undefined) {
        globalThis.clearTimeout(timeoutId);
      }
    };
  }, []);

  return null;
}
