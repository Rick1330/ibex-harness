"use client";

import { useEffect, useState } from "react";

import { SectionShell } from "@/components/chrome/section-shell";
import { cn } from "@/lib/cn";
import { REQUEST_PATH } from "@/lib/landing-content";

/** §03 · Request Path — horizontal trace showpiece (design §6). */
export function LandingFlow() {
  const [active, setActive] = useState(0);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    if (typeof globalThis.matchMedia !== "function") return;
    const media = globalThis.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReducedMotion(media.matches);
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, []);

  useEffect(() => {
    if (reducedMotion) return;
    const timer = globalThis.setInterval(() => {
      setActive((current) => (current + 1) % REQUEST_PATH.length);
    }, 3000);
    return () => globalThis.clearInterval(timer);
  }, [reducedMotion]);

  return (
    <SectionShell
      id="request-path"
      section="§03"
      label="REQUEST PATH"
      meta="trace_id  7f3a…c21   ·   duration  17.4ms   ·   status  200"
      docHref="/docs/architecture/overview"
    >
      <div className="rounded-md border border-border bg-surface-1 p-6 sm:p-8">
        <div className="grid gap-8 md:grid-cols-4">
          {REQUEST_PATH.map((node, index) => (
            <div key={node.step} className="relative min-w-0">
              {index < REQUEST_PATH.length - 1 ? (
                <span
                  className="pointer-events-none absolute left-[calc(100%-0.25rem)] top-4 hidden h-px w-[calc(100%-1.5rem)] bg-border md:block"
                  aria-hidden
                >
                  <span
                    className={cn(
                      "absolute top-1/2 size-1.5 -translate-y-1/2 rounded-full bg-accent transition-all duration-500",
                      active === index ? "left-1/2 opacity-100" : "left-0 opacity-0",
                    )}
                  />
                </span>
              ) : null}
              <div
                className={cn(
                  "mb-3 inline-flex size-8 items-center justify-center rounded-sm border font-mono text-xs transition-colors",
                  active === index
                    ? "border-accent text-accent"
                    : "border-border text-foreground",
                )}
              >
                {node.step}
              </div>
              <p className="font-medium">{node.name}</p>
              <pre className="mt-3 whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-foreground-subtle">
                {node.snippet}
              </pre>
            </div>
          ))}
        </div>
      </div>
    </SectionShell>
  );
}
