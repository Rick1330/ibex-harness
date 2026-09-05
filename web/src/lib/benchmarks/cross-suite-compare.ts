export type SuiteColumnId =
  | "proxy"
  | "hnsw"
  | "rankingQuality"
  | "writePipeline"
  | "extractionQuality";

export type SuiteLatestSnapshot = Readonly<{
  id: SuiteColumnId;
  label: string;
  shortSha: string | null;
  status: string | null;
  timestamp: string | null;
  /** Suite-specific headline metrics already formatted for display. */
  metrics: readonly Readonly<{ label: string; value: string }>[];
}>;

export type CrossSuiteRow = Readonly<{
  label: string;
  cells: Readonly<Record<SuiteColumnId, string>>;
}>;

const EMPTY = "—";

function emptyCells(columns: readonly SuiteColumnId[]): Record<SuiteColumnId, string> {
  const cells = {} as Record<SuiteColumnId, string>;
  for (const id of columns) {
    cells[id] = EMPTY;
  }
  return cells;
}

function sharedIdentityRows(
  columns: readonly SuiteColumnId[],
  byId: Map<SuiteColumnId, SuiteLatestSnapshot>,
): CrossSuiteRow[] {
  const cellFor = (
    pick: (snapshot: SuiteLatestSnapshot | undefined) => string | null | undefined,
  ): Record<SuiteColumnId, string> =>
    Object.fromEntries(
      columns.map((id) => [id, pick(byId.get(id)) ?? EMPTY]),
    ) as Record<SuiteColumnId, string>;

  return [
    { label: "Latest SHA", cells: cellFor((s) => s?.shortSha) },
    { label: "Status", cells: cellFor((s) => s?.status) },
    { label: "When", cells: cellFor((s) => s?.timestamp) },
  ];
}

function collectMetricLabels(snapshots: readonly SuiteLatestSnapshot[]): string[] {
  const labels: string[] = [];
  const seen = new Set<string>();
  for (const snapshot of snapshots) {
    for (const metric of snapshot.metrics) {
      if (!seen.has(metric.label)) {
        seen.add(metric.label);
        labels.push(metric.label);
      }
    }
  }
  return labels;
}

function metricRowsFor(
  labels: readonly string[],
  snapshots: readonly SuiteLatestSnapshot[],
  columns: readonly SuiteColumnId[],
): CrossSuiteRow[] {
  return labels.map((label) => {
    const cells = emptyCells(columns);
    for (const snapshot of snapshots) {
      const match = snapshot.metrics.find((metric) => metric.label === label);
      if (match) {
        cells[snapshot.id] = match.value;
      }
    }
    return { label, cells };
  });
}

/**
 * Build a matrix: shared identity rows first, then every suite metric label.
 * Suites that lack a metric show "—" (compare what exists, don't invent parity).
 */
export function buildCrossSuiteCompareRows(
  snapshots: readonly SuiteLatestSnapshot[],
): CrossSuiteRow[] {
  const columns = snapshots.map((snapshot) => snapshot.id);
  const byId = new Map(snapshots.map((snapshot) => [snapshot.id, snapshot]));
  const shared = sharedIdentityRows(columns, byId);
  const metricRows = metricRowsFor(collectMetricLabels(snapshots), snapshots, columns);
  return [...shared, ...metricRows];
}
