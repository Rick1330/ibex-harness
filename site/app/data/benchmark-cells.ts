/**
 * HNSW corpus cells: labels, coverage, and the cell that carries the latency gate.
 *
 * Deliberately free of the published-JSON imports so the selection and labelling
 * rules can be unit-tested against synthetic runs — reordered cells, missing
 * cells, a tail-latency-only failure, an empty run — without depending on which
 * sizes or verdicts today's artifact holds.
 */

/** Corpus size the publisher's HNSW latency gate is defined against. */
export const HNSW_GATE_CORPUS = 1_000_000

/** Corpus sizes the published profile is expected to carry; a gap is reported. */
export const HNSW_PROFILE = [10_000, 100_000, 1_000_000] as const

/** The only field the selection and labelling rules read from a published cell. */
export interface CorpusCell {
  readonly corpus_size: number
}

/** A published cell carrying the values the gate description quotes. */
export interface ScoredCell extends CorpusCell {
  readonly recall_at_10: number
  readonly latency_ms_p95: number
  readonly latency_ms_p99: number
}

/**
 * The publisher's gate summary, as published in `hnsw-benchmark-data.json`.
 *
 * `recall_ok`, `p95_1m_ok`, and `p99_1m_ok` are the publisher's own verdicts
 * (`publish_cells.py::compute_status`), because the artifact publishes the two
 * latency limits only as those booleans, not as numbers.
 */
export interface HnswGateSummary {
  readonly recall_floor: number
  readonly worst_recall_at_10?: number
  readonly recall_ok?: boolean
  readonly p95_1m_ok?: boolean
  readonly p99_1m_ok?: boolean
}

const GROUPED = new Intl.NumberFormat('en-US')
const MILLISECONDS = new Intl.NumberFormat('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const SHARE = new Intl.NumberFormat('en-US', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 })

const CORPUS_UNITS = [
  { scale: 1_000_000_000, suffix: 'B' },
  { scale: 1_000_000, suffix: 'M' },
  { scale: 1_000, suffix: 'k' },
] as const

const isFiniteNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)

/**
 * The two latency percentiles the publisher gates, named once so every sentence
 * and row label below interpolates the same token. The values they label come
 * from `hnsw-benchmark-data.json`; these are labels, not measurements.
 */
const P95 = 'p95'
const P99 = 'p99'

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

/** A millisecond value from the artifact, or `—` when it carries none. */
function formatMs(value: number | undefined): string {
  return isFiniteNumber(value) ? `${MILLISECONDS.format(value)} ms` : '—'
}

/** A share from the artifact as a percentage, or `—` when it carries none. */
function formatShare(value: number | undefined): string {
  return isFiniteNumber(value) ? SHARE.format(value) : '—'
}

/** `a`, `a and b`, `a, b and c`: the wording of a failed-criteria list. */
function listWords(items: readonly string[]): string {
  if (items.length < 2) return items.join('')
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
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
 * The worst recall across the published cells: the recall the publisher gates,
 * not the mean the page headlines.
 *
 * The summary's own `worst_recall_at_10` wins when published; the cells are the
 * fallback, because `compute_gate_summary` takes `min` over exactly those cells.
 */
export function hnswWorstRecall(cells: readonly ScoredCell[], gate: HnswGateSummary): number | undefined {
  if (isFiniteNumber(gate.worst_recall_at_10)) return gate.worst_recall_at_10
  if (!cells.length) return undefined
  return Math.min(...cells.map(cell => cell.recall_at_10))
}

export type HnswGateCriterion = 'recall' | typeof P95 | typeof P99

export interface HnswGateCheck {
  readonly criterion: HnswGateCriterion
  /** The criterion's name in a sentence: `worst recall`, or the percentile. */
  readonly label: string
  /** The publisher's verdict; `undefined` when the artifact publishes none. */
  readonly ok: boolean | undefined
}

/**
 * The publisher's three gate criteria in the order `compute_status` applies
 * them: worst recall against the floor, then the two latency percentiles at the
 * gate cell.
 * `compute_status` fails a run when recall fails **or** either latency fails, so
 * all three are reported together and none may stand for the gate alone.
 */
export function hnswGateChecks(cells: readonly ScoredCell[], gate: HnswGateSummary): HnswGateCheck[] {
  const worst = hnswWorstRecall(cells, gate)
  const recallOk = gate.recall_ok ?? (worst === undefined ? undefined : worst >= gate.recall_floor)
  return [
    { criterion: 'recall', label: 'worst recall', ok: recallOk },
    { criterion: P95, label: P95, ok: gate.p95_1m_ok },
    { criterion: P99, label: P99, ok: gate.p99_1m_ok },
  ]
}

/** Labels of the criteria the publisher's verdict marks as failed. */
function failedLabels(checks: readonly HnswGateCheck[]): string[] {
  return checks.filter(check => check.ok === false).map(check => check.label)
}

/** The sentence naming the failed criteria, or the all-hold / no-verdict outcome. */
function gateOutcome(checks: readonly HnswGateCheck[]): string {
  const failed = failedLabels(checks)
  if (failed.length) return `Fails on ${listWords(failed)}.`
  if (checks.some(check => check.ok === undefined)) return 'The publisher published no verdict for at least one criterion.'
  return 'All three hold.'
}

/**
 * Compact gate line for a card header: every criterion the publisher applies and
 * the outcome, so no single row can stand for the gate.
 */
export function hnswGateHeadline(cells: readonly ScoredCell[], gate: HnswGateSummary): string {
  const checks = hnswGateChecks(cells, gate)
  const criteria = checks.map(check => check.label).join(' · ')
  const failed = failedLabels(checks)
  if (failed.length) return `${criteria} · fails ${failed.join(', ')}`
  return `${criteria} · ${checks.some(check => check.ok === undefined) ? 'verdict not published' : 'pass'}`
}

/**
 * The gate in one sentence: every criterion the publisher applies, the value each
 * was measured at, and which one failed.
 */
export function hnswGateText(cells: readonly ScoredCell[], gate: HnswGateSummary): string {
  const checks = hnswGateChecks(cells, gate)
  const recall = `worst recall ${formatShare(hnswWorstRecall(cells, gate))} against the ${formatShare(gate.recall_floor)} floor`
  const cell = hnswGateCell(cells)
  if (!cell) {
    return `Gate criteria: ${recall}; ${P95} and ${P99} are not measured, because no published cell reaches ${formatCorpusSize(HNSW_GATE_CORPUS)}.`
  }
  const latencies = `${P95} ${formatMs(cell.latency_ms_p95)} and ${P99} ${formatMs(cell.latency_ms_p99)} at ${formatCorpusSize(cell.corpus_size)} (the first published cell at or above ${formatCorpusSize(HNSW_GATE_CORPUS)}) against the publisher's latency limits`
  return `Gate criteria: ${recall}, and ${latencies}. ${gateOutcome(checks)}`
}

/**
 * One line of coverage for the HNSW surfaces: the published sizes in ascending
 * order, the reported gaps, and all three criteria the publisher gates.
 */
export function hnswCoverage(cells: readonly ScoredCell[], gate: HnswGateSummary): string {
  if (!cells.length) {
    return `No HNSW cells are published for this run, so nothing reaches the ${formatCorpusSize(HNSW_GATE_CORPUS)} gate.`
  }
  const published = sortHnswCells(cells).map(cell => formatCorpusSize(cell.corpus_size)).join(', ')
  const parts = [`Published cells: ${published}.`]
  const missing = hnswMissingCells(cells)
  if (missing.length) parts.push(`Not reported: ${missing.map(formatCorpusSize).join(', ')}.`)
  parts.push(hnswGateText(cells, gate))
  return parts.join(' ')
}

export interface HnswSummaryRow<T extends CorpusCell> {
  cell: T
  label: string
  value: string
  note: string | undefined
  /** The cell the publisher's gate summary read; true for exactly one row. */
  gate: boolean
}

/**
 * The latency summary rows the HNSW modals show: one per published cell,
 * ascending, each labelled with its own size and followed by its tail latency.
 *
 * The gate note marks exactly the cell `hnswGateCell` returns, and says it
 * carries the gate metrics: the row shows both latency percentiles because the
 * publisher fails a run on either. Worst recall is a separate summary row.
 */
export function hnswSummaryRows<T extends ScoredCell>(cells: readonly T[]): HnswSummaryRow<T>[] {
  const gate = hnswGateCell(cells)
  return sortHnswCells(cells).map((cell) => {
    const isGate = cell === gate
    const tail = `${P99} ${formatMs(cell.latency_ms_p99)}`
    return {
      cell,
      label: `${P95} at ${formatCorpusSize(cell.corpus_size)}`,
      value: formatMs(cell.latency_ms_p95),
      note: isGate ? `${tail} · gate metrics` : tail,
      gate: isGate,
    }
  })
}
