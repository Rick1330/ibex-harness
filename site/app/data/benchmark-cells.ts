/**
 * HNSW corpus cells: labels, coverage, and the cell that carries the latency gate.
 *
 * Deliberately free of the published-JSON imports so the selection and labelling
 * rules can be unit-tested against synthetic runs — reordered cells, missing
 * cells, an empty run — without depending on which sizes today's artifact holds.
 */

/** Corpus size the publisher's HNSW latency gate is defined against. */
export const HNSW_GATE_CORPUS = 1_000_000

/** Corpus sizes the published profile is expected to carry; a gap is reported. */
export const HNSW_PROFILE = [10_000, 100_000, 1_000_000] as const

/** The only field the selection and labelling rules read from a published cell. */
export interface CorpusCell {
  readonly corpus_size: number
}

const GROUPED = new Intl.NumberFormat('en-US')

const CORPUS_UNITS = [
  { scale: 1_000_000_000, suffix: 'B' },
  { scale: 1_000_000, suffix: 'M' },
  { scale: 1_000, suffix: 'k' },
] as const

/**
 * `10000 → 10k`, `1000000 → 1M`, `1500000 → 1.5M`, `500000 → 500k`.
 *
 * A size that is not an exact multiple of its unit keeps every digit
 * (`1234567 → 1,234,567`), so two different corpora never print the same label.
 */
export function formatCorpusSize(size: number): string {
  if (!Number.isFinite(size)) return '—'
  for (const { scale, suffix } of CORPUS_UNITS) {
    if (size < scale) continue
    if (size % scale === 0) return `${GROUPED.format(size / scale)}${suffix}`
    if (size % (scale / 10) === 0) return `${(size / scale).toFixed(1)}${suffix}`
    break
  }
  return GROUPED.format(size)
}

/** Cells in ascending corpus order: display order never follows data order. */
export function sortHnswCells<T extends CorpusCell>(cells: readonly T[]): T[] {
  return [...cells].sort((a, b) => a.corpus_size - b.corpus_size)
}

/**
 * The published cell that carries the latency gate.
 *
 * `benchmarks/memory/publish_cells.py::compute_gate_summary` gates the first
 * surviving cell with `corpus_size >= 1_000_000`, so a 2M-only publication is
 * gated on 2M. Selecting an exact 1M cell instead would badge a row the
 * publisher never gated, or badge nothing when a larger cell is the gate.
 */
export function hnswGateCell<T extends CorpusCell>(cells: readonly T[]): T | undefined {
  return cells.find(cell => cell.corpus_size >= HNSW_GATE_CORPUS)
}

/**
 * The largest published cell: the worst-case latency point, and the fallback
 * when no cell reaches the gate.
 *
 * Returns `undefined` for an empty run rather than throwing: the page renders an
 * empty state, and a throw here would take the whole server-rendered route down
 * instead of one card.
 */
export function largestHnswCell<T extends CorpusCell>(cells: readonly T[]): T | undefined {
  return cells.reduce<T | undefined>(
    (largest, cell) => (largest && largest.corpus_size >= cell.corpus_size ? largest : cell),
    undefined,
  )
}

/** Profile sizes with no published cell, in profile order. */
export function hnswMissingCells(cells: readonly CorpusCell[]): number[] {
  return HNSW_PROFILE.filter(size => !cells.some(cell => cell.corpus_size === size))
}

/**
 * One line of coverage for the HNSW surfaces: the published sizes in ascending
 * order, the reported gaps, and the cell the gate is measured on.
 */
export function hnswCoverage(cells: readonly CorpusCell[]): string {
  if (!cells.length) {
    return `No HNSW cells are published for this run, so nothing reaches the ${formatCorpusSize(HNSW_GATE_CORPUS)} gate.`
  }
  const published = sortHnswCells(cells).map(cell => formatCorpusSize(cell.corpus_size)).join(', ')
  const parts = [`Published cells: ${published}.`]
  const missing = hnswMissingCells(cells)
  if (missing.length) parts.push(`Not reported: ${missing.map(formatCorpusSize).join(', ')}.`)
  const gate = hnswGateCell(cells)
  parts.push(gate
    ? `Gate metric: p95 at ${formatCorpusSize(gate.corpus_size)}, the first published cell at or above ${formatCorpusSize(HNSW_GATE_CORPUS)}.`
    : `Gate metric: none, because no published cell reaches ${formatCorpusSize(HNSW_GATE_CORPUS)}.`)
  return parts.join(' ')
}

export interface HnswSummaryRow<T extends CorpusCell> {
  cell: T
  label: string
  note: 'gate metric' | undefined
}

/**
 * The latency summary rows the HNSW modals show: one per published cell,
 * ascending, each labelled with its own size. The gate note marks exactly the
 * cell `hnswGateCell` returns — the row the publisher's gate summary read.
 */
export function hnswSummaryRows<T extends CorpusCell>(cells: readonly T[]): HnswSummaryRow<T>[] {
  const gate = hnswGateCell(cells)
  return sortHnswCells(cells).map(cell => ({
    cell,
    label: `p95 at ${formatCorpusSize(cell.corpus_size)}`,
    note: cell === gate ? 'gate metric' : undefined,
  }))
}
