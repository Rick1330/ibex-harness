"use client";

import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";
import { HERO_TERMINAL_PANELS } from "@/lib/landing-content";

const TAB_IDS = ["request", "response", "trace"] as const;
type TabId = (typeof TAB_IDS)[number];

const TAB_LABELS: Record<TabId, string> = {
  request: "request.http",
  response: "response.json",
  trace: "trace.log",
};

const TONE_CLASS: Record<string, string> = {
  default: "text-[oklch(0.92_0.01_90)]",
  muted: "text-[oklch(0.65_0.01_80)]",
  accent: "text-[oklch(0.72_0.16_48)]",
  success: "text-[oklch(0.72_0.14_155)]",
};

function panelForTab(tab: TabId) {
  return (
    HERO_TERMINAL_PANELS.find((panel) => panel.id === tab) ??
    HERO_TERMINAL_PANELS[0]
  );
}

export function HeroTerminalCard() {
  const [activeTab, setActiveTab] = useState<TabId>("request");
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
      setActiveTab((current) => {
        const index = TAB_IDS.indexOf(current);
        return TAB_IDS[(index + 1) % TAB_IDS.length];
      });
    }, 6000);
    return () => globalThis.clearInterval(timer);
  }, [reducedMotion]);

  const panel = panelForTab(activeTab);

  return (
    <div
      className="overflow-hidden rounded-md border border-border bg-[oklch(0.145_0.004_60)] text-[oklch(0.955_0.006_88)]"
      data-testid="hero-terminal-card"
    >
      <div className="flex items-center gap-2 border-b border-white/10 px-4 py-2.5">
        <span className="size-2 rounded-full bg-white/25" aria-hidden />
        <span className="size-2 rounded-full bg-white/25" aria-hidden />
        <span className="size-2 rounded-full bg-white/25" aria-hidden />
        <span className="ml-2 truncate font-mono text-[11px] text-white/50">
          ~/ibex
        </span>
      </div>

      <div
        className="flex border-b border-white/10"
        role="tablist"
        aria-label="Terminal views"
      >
        {TAB_IDS.map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={activeTab === tab}
            className={cn(
              "border-b-2 px-3 py-2 font-mono text-[11px] transition-colors",
              activeTab === tab
                ? "border-[oklch(0.72_0.16_48)] text-white"
                : "border-transparent text-white/45 hover:text-white/80",
            )}
            onClick={() => setActiveTab(tab)}
          >
            {TAB_LABELS[tab]}
          </button>
        ))}
      </div>

      <pre
        className="min-h-[180px] overflow-x-auto p-4 font-mono text-[13px] leading-relaxed"
        role="tabpanel"
      >
        {panel.lines.map((line) => (
          <span key={line.text} className="block">
            {line.parts.map((part) => (
              <span
                key={`${line.text}-${part.text}`}
                className={TONE_CLASS[part.tone ?? "default"]}
              >
                {part.text}
              </span>
            ))}
          </span>
        ))}
        <span className="caret-block mt-1 bg-white/80" aria-hidden />
      </pre>

      <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-white/10 px-4 py-2 font-mono text-[11px] text-white/45">
        <span>P99 17ms</span>
        <span>tenant acme-prod</span>
        <span>model gpt-4o</span>
      </div>
    </div>
  );
}
