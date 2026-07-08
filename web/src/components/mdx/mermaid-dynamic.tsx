"use client";

import dynamic from "next/dynamic";

export const Mermaid = dynamic(
  () => import("./mermaid").then((mod) => mod.Mermaid),
  {
    ssr: false,
    loading: () => (
      <div
        aria-hidden
        className="mermaid-diagram my-8 min-h-[12rem] animate-pulse rounded-[4px] border border-border bg-panel"
      />
    ),
  },
);
