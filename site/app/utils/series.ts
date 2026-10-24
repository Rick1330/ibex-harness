// Shared series palette for the benchmark charts: the first three series get
// distinct colors and everything beyond falls back to violet, matching the
// legend order on the benchmarks page.
const SERIES_COLORS = ['var(--chart-lime)', 'var(--chart-blue)', 'var(--chart-pink)', 'var(--chart-violet)'] as const

export function seriesColor(index: number): string {
  return SERIES_COLORS[index] ?? SERIES_COLORS[SERIES_COLORS.length - 1]!
}
