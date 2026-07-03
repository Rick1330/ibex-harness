"use client";

import type { AppRouterInstance } from "next/dist/shared/lib/app-router-context.shared-runtime";
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

type KeyboardDispatchContext = Readonly<{
  event: KeyboardEvent;
  pageRuns: BenchmarkRun[];
  selectedIndex: number;
  setSelectedIndex: (index: number) => void;
  onToggleCompare: (sha: string) => void;
  onShowHelp: () => void;
  helpOpen: boolean;
  statusFilterId: string;
  router: AppRouterInstance;
}>;

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName;
  return tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || target.isContentEditable;
}

function moveSelection(
  event: KeyboardEvent,
  pageRuns: BenchmarkRun[],
  selectedIndex: number,
  setSelectedIndex: (index: number) => void,
  delta: number,
): boolean {
  event.preventDefault();
  const next = Math.max(0, Math.min(pageRuns.length - 1, selectedIndex + delta));
  setSelectedIndex(next);
  return true;
}

function openSelectedRun(
  event: KeyboardEvent,
  pageRuns: BenchmarkRun[],
  selectedIndex: number,
  router: AppRouterInstance,
): boolean {
  const run = pageRuns[selectedIndex];
  if (!run) {
    return false;
  }
  event.preventDefault();
  router.push(`/benchmarks/history/${run.short_sha}`);
  return true;
}

function toggleSelectedCompare(
  event: KeyboardEvent,
  pageRuns: BenchmarkRun[],
  selectedIndex: number,
  onToggleCompare: (sha: string) => void,
): boolean {
  const run = pageRuns[selectedIndex];
  if (!run) {
    return false;
  }
  event.preventDefault();
  onToggleCompare(run.short_sha);
  return true;
}

function focusStatusFilter(event: KeyboardEvent, statusFilterId: string): boolean {
  event.preventDefault();
  document.getElementById(statusFilterId)?.focus();
  return true;
}

function dispatchBenchmarkKey(ctx: KeyboardDispatchContext): boolean {
  const { event } = ctx;

  if (event.key === "?" && !event.metaKey && !event.ctrlKey) {
    event.preventDefault();
    ctx.onShowHelp();
    return true;
  }

  if (ctx.helpOpen) {
    return false;
  }

  if (event.key === "j" || event.key === "ArrowDown") {
    return moveSelection(event, ctx.pageRuns, ctx.selectedIndex, ctx.setSelectedIndex, 1);
  }

  if (event.key === "k" || event.key === "ArrowUp") {
    return moveSelection(event, ctx.pageRuns, ctx.selectedIndex, ctx.setSelectedIndex, -1);
  }

  if (event.key === "Enter") {
    return openSelectedRun(event, ctx.pageRuns, ctx.selectedIndex, ctx.router);
  }

  if (event.key === "c") {
    return toggleSelectedCompare(event, ctx.pageRuns, ctx.selectedIndex, ctx.onToggleCompare);
  }

  if (event.key === "/") {
    return focusStatusFilter(event, ctx.statusFilterId);
  }

  return false;
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
      dispatchBenchmarkKey({
        event,
        pageRuns,
        selectedIndex,
        setSelectedIndex,
        onToggleCompare,
        onShowHelp,
        helpOpen,
        statusFilterId,
        router,
      });
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
