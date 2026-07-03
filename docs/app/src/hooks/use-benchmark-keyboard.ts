"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import type { BenchmarkRun } from "@/lib/benchmarks/types";

type UseBenchmarkKeyboardOptions = Readonly<{
  pageRuns: BenchmarkRun[];
  selectedIndex: number;
  setSelectedIndex: (index: number) => void;
  onToggleCompare: (sha: string) => void;
  onShowHelp: () => void;
  helpOpen: boolean;
  statusFilterId: string;
}>;

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName;
  return tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || target.isContentEditable;
}

export function useBenchmarkKeyboard({
  pageRuns,
  selectedIndex,
  setSelectedIndex,
  onToggleCompare,
  onShowHelp,
  helpOpen,
  statusFilterId,
}: UseBenchmarkKeyboardOptions) {
  const router = useRouter();

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target)) {
        return;
      }

      if (event.key === "?" && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        onShowHelp();
        return;
      }

      if (helpOpen) {
        return;
      }

      if (event.key === "j" || event.key === "ArrowDown") {
        event.preventDefault();
        setSelectedIndex(Math.min(pageRuns.length - 1, selectedIndex + 1));
        return;
      }

      if (event.key === "k" || event.key === "ArrowUp") {
        event.preventDefault();
        setSelectedIndex(Math.max(0, selectedIndex - 1));
        return;
      }

      if (event.key === "Enter") {
        const run = pageRuns[selectedIndex];
        if (run) {
          event.preventDefault();
          router.push(`/benchmarks/history/${run.short_sha}`);
        }
        return;
      }

      if (event.key === "c") {
        const run = pageRuns[selectedIndex];
        if (run) {
          event.preventDefault();
          onToggleCompare(run.short_sha);
        }
        return;
      }

      if (event.key === "/") {
        event.preventDefault();
        document.getElementById(statusFilterId)?.focus();
      }
    };

    globalThis.addEventListener("keydown", handler);
    return () => globalThis.removeEventListener("keydown", handler);
  }, [
    onShowHelp,
    onToggleCompare,
    pageRuns,
    router,
    selectedIndex,
    setSelectedIndex,
    statusFilterId,
    helpOpen,
  ]);

  return {};
}
