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

type SelectionState = Readonly<{
  pageRuns: BenchmarkRun[];
  selectedIndex: number;
  setSelectedIndex: (index: number) => void;
}>;

type KeyboardDispatchContext = SelectionState &
  Readonly<{
    event: KeyboardEvent;
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
  state: SelectionState,
  delta: number,
): boolean {
  event.preventDefault();
  const next = Math.max(0, Math.min(state.pageRuns.length - 1, state.selectedIndex + delta));
  state.setSelectedIndex(next);
  return true;
}

function withSelectedRun(
  event: KeyboardEvent,
  state: SelectionState,
  action: (run: BenchmarkRun) => void,
): boolean {
  const run = state.pageRuns.at(state.selectedIndex);
  if (!run) {
    return false;
  }
  event.preventDefault();
  action(run);
  return true;
}

function focusStatusFilter(event: KeyboardEvent, statusFilterId: string): boolean {
  event.preventDefault();
  document.getElementById(statusFilterId)?.focus();
  return true;
}

function handleHelpKey(ctx: KeyboardDispatchContext): boolean {
  const { event } = ctx;
  if (event.metaKey || event.ctrlKey) {
    return false;
  }
  event.preventDefault();
  ctx.onShowHelp();
  return true;
}

function handleArrowDown(ctx: KeyboardDispatchContext): boolean {
  return moveSelection(ctx.event, ctx, 1);
}

function handleArrowUp(ctx: KeyboardDispatchContext): boolean {
  return moveSelection(ctx.event, ctx, -1);
}

function handleEnter(ctx: KeyboardDispatchContext): boolean {
  return withSelectedRun(ctx.event, ctx, (run) => {
    ctx.router.push(`/benchmarks/history/${run.short_sha}`);
  });
}

function handleCompare(ctx: KeyboardDispatchContext): boolean {
  return withSelectedRun(ctx.event, ctx, (run) => {
    ctx.onToggleCompare(run.short_sha);
  });
}

const KEY_BINDINGS: ReadonlyArray<
  readonly [readonly string[], (ctx: KeyboardDispatchContext) => boolean]
> = [
  [["?"], handleHelpKey],
  [["j", "ArrowDown"], handleArrowDown],
  [["k", "ArrowUp"], handleArrowUp],
  [["Enter"], handleEnter],
  [["c"], handleCompare],
  [["/"], (ctx) => focusStatusFilter(ctx.event, ctx.statusFilterId)],
];

function dispatchBenchmarkKey(ctx: KeyboardDispatchContext): boolean {
  if (ctx.helpOpen && ctx.event.key !== "?") {
    return false;
  }

  for (const [keys, handler] of KEY_BINDINGS) {
    if (keys.includes(ctx.event.key)) {
      return handler(ctx);
    }
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
    return () => { globalThis.removeEventListener("keydown", handler); };
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
