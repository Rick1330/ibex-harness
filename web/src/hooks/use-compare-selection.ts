"use client";

import { useCallback, useState } from "react";

import type { BenchmarkRun } from "@/lib/benchmarks/types";

const MAX_COMPARE = 2;

export function useCompareSelection() {
  const [selected, setSelected] = useState<string[]>([]);

  const toggle = useCallback((sha: string) => {
    setSelected((current) => {
      if (current.includes(sha)) {
        return current.filter((value) => value !== sha);
      }
      if (current.length >= MAX_COMPARE) {
        return [current[1], sha];
      }
      return [...current, sha];
    });
  }, []);

  const clear = useCallback(() => {
    setSelected([]);
  }, []);

  const isSelected = useCallback((sha: string) => selected.includes(sha), [selected]);

  function compareQuery(): string | null {
    if (selected.length !== MAX_COMPARE) {
      return null;
    }
    const [base, head] = selected;
    return `base=${base}&head=${head}`;
  }

  function selectedRuns(runs: BenchmarkRun[]): BenchmarkRun[] {
    return selected
      .map((sha) => runs.find((run) => run.short_sha === sha || run.sha === sha))
      .filter((run): run is BenchmarkRun => run !== undefined);
  }

  return {
    selected,
    toggle,
    clear,
    isSelected,
    compareQuery,
    selectedRuns,
    canCompare: selected.length === MAX_COMPARE,
  };
}
