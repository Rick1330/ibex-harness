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
  default: "text-foreground",
  muted: "text-foreground-muted",
  accent: "text-accent",
  success: "text-success",
};

function panelForTab(tab: TabId) {
  return (
    HERO_TERMINAL_PANELS.find((panel) => panel.id === tab) ??
    HERO_TERMINAL_PANELS[0]
  );
}

/** §01 right column — cycling terminal card (design §6). Tokens only. */
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
      className="overflow-hidden rounded-md border border-border bg-surface-1"
      data-testid="hero-terminal-card"
    >
      <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
        <span className="size-2 rounded-full bg-foreground-subtle" aria-hidden />
        <span className="size-2 rounded-full bg-foreground-subtle" aria-hidden />
        <span className="size-2 rounded-full bg-foreground-subtle" aria-hidden />
        <span className="ml-2 truncate font-mono text-[11px] text-foreground-muted">
          ~/ibex/trace-7f3a…c21
        </span>
      </div>

      <div
        className="flex border-b border-border"
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
                ? "border-accent text-foreground"
                : "border-transparent text-foreground-muted hover:text-foreground",
            )}
            onClick={() => setActiveTab(tab)}
          >
            {TAB_LABELS[tab]}
          </button>
        ))}
      </div>

      <pre
        className="min-h-[200px] overflow-x-auto p-4 font-mono text-[13px] leading-relaxed"
        style={{ fontVariantNumeric: "tabular-nums" }}
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
        <span className="caret-block" aria-hidden />
      </pre>

      <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-border px-4 py-2 font-mono text-[11px] text-foreground-muted">
        <span>P99 17ms</span>
        <span>tenant acme-prod</span>
        <span>model gpt-4o</span>
      </div>
    </div>
  );
}
