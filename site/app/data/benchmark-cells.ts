/**
 * HNSW corpus cells: labels, coverage, and the cell that carries the latency gate.
 *
 * Deliberately free of the published-JSON imports so the selection and labelling
 * rules can be unit-tested against synthetic runs — reordered cells, missing
 * cells, a tail-latency-only failure, a fast run with deferred latency, an empty
 * run — without depending on which sizes or verdicts today's artifact holds.
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
 *
 * `has_1m` is the publisher's own flag for "a published cell reaches the latency
 * gate". It is what `_1m_latency_failed` branches on, so it decides whether a
 * missing latency verdict means *deferred* or *unknown*.
 */
export interface HnswGateSummary {
  readonly recall_floor: number
  readonly worst_recall_at_10?: number
  readonly recall_ok?: boolean
  readonly has_1m?: boolean
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

/**
 * How one criterion stands, in the publisher's own terms:
 *
 * - `hold` — the publisher's verdict is a pass;
 * - `fail` — the publisher's verdict is a fail;
 * - `deferred` — no published cell reaches the gate, so there is nothing to
 *   measure. `publish_cells.py::_1m_latency_failed` returns `False` when
 *   `has_1m` is false, and its docstring calls a missing 1M on the smoke and
 *   fast profiles "expected coverage deferral, not a soft failure" — so this
 *   state neither passes nor fails the criterion, it postpones it;
 * - `unknown` — a gate cell exists but the artifact carries no verdict for it.
 *   Nothing can be said either way, so the page fails closed.
 */
export type HnswGateCriterionState = 'hold' | 'fail' | 'deferred' | 'unknown'

export interface HnswGateCheck {
  readonly criterion: HnswGateCriterion
  /** The criterion's name in a sentence: `worst recall`, or the percentile. */
  readonly label: string
  readonly state: HnswGateCriterionState
  /** The publisher's verdict; `undefined` when the artifact publishes none. */
  readonly ok: boolean | undefined
}

/**
 * Whether the publisher measured the two latency criteria, read as
 * `_1m_latency_failed` reads it: `has_1m` decides.
 *
 * The flag is the publisher's own, computed from the same cell list it publishes,
 * so it and the scan below cannot disagree in a valid artifact. They are read as
 * a union so an artifact edited into disagreement still fails closed rather than
 * claiming a deferral it has no flag for, or a measurement it has no cell for.
 */
function latencyGated(cells: readonly CorpusCell[], gate: HnswGateSummary): boolean {
  return gate.has_1m === true || hnswGateCell(cells) !== undefined
}

function latencyState(verdict: boolean | undefined, gated: boolean): HnswGateCriterionState {
  if (!gated) return 'deferred'
  if (verdict === undefined) return 'unknown'
  return verdict ? 'hold' : 'fail'
}

/**
 * The publisher's three gate criteria in the order `compute_status` applies
 * them: worst recall against the floor, then the two latency percentiles at the
 * gate cell. `compute_status` fails a run when recall fails **or** either latency
 * fails, and a deferred criterion is never a failure, so all three are reported
 * together with how each one stands and none may stand for the gate alone.
 */
export function hnswGateChecks(cells: readonly ScoredCell[], gate: HnswGateSummary): HnswGateCheck[] {
  const worst = hnswWorstRecall(cells, gate)
  const recallOk = gate.recall_ok ?? (worst === undefined ? undefined : worst >= gate.recall_floor)
  const gated = latencyGated(cells, gate)
  return [
    {
      criterion: 'recall',
      label: 'worst recall',
      ok: recallOk,
      state: recallOk === undefined ? 'unknown' : recallOk ? 'hold' : 'fail',
    },
    { criterion: P95, label: P95, ok: gate.p95_1m_ok, state: latencyState(gate.p95_1m_ok, gated) },
    { criterion: P99, label: P99, ok: gate.p99_1m_ok, state: latencyState(gate.p99_1m_ok, gated) },
  ]
}

export type HnswGateStatus = 'pass' | 'fail' | 'unknown'

export interface HnswGateVerdict {
  readonly status: HnswGateStatus
  /** Criteria the publisher's verdict marks as failed; empty unless `fail`. */
  readonly failed: readonly string[]
  /** Criteria postponed for want of a gate cell; empty when the run was gated. */
  readonly deferred: readonly string[]
  /** Criteria carrying no interpretable verdict; empty unless `unknown`. */
  readonly missing: readonly string[]
}

/**
 * The run's verdict, from the publisher's own three-branch rule
 * (`publish_cells.py::compute_status`):
 *
 * 1. worst recall below the floor fails the run;
 * 2. otherwise a run with no cell at or above the gate passes, with the two
 *    latency criteria deferred — the publisher does not fail a fast or smoke
 *    profile for the coverage it does not claim to have;
 * 3. otherwise either latency verdict failing fails the run.
 *
 * Recall is decided first, as `compute_status` decides it, so a recall failure is
 * still reported when a latency criterion is deferred or unreadable.
 *
 * One case is deliberately stricter than `compute_status`: when a gate cell
 * exists but the artifact publishes no latency verdict, `compute_status` defaults
 * each to `True` (`gate.get("p95_1m_ok", True)`) and reports a pass. A missing
 * field is not evidence of a pass, so the verdict is `unknown` and every
 * rendering says "verdict not published".
 */
export function hnswGateVerdict(cells: readonly ScoredCell[], gate: HnswGateSummary): HnswGateVerdict {
  const checks = hnswGateChecks(cells, gate)
  const deferred = checks.filter(check => check.state === 'deferred').map(check => check.label)
  const failed = checks.filter(check => check.state === 'fail').map(check => check.label)
  if (failed.length) return { status: 'fail', failed, deferred, missing: [] }
  const missing = checks.filter(check => check.state === 'unknown').map(check => check.label)
  if (missing.length) return { status: 'unknown', failed, deferred, missing }
  return { status: 'pass', failed: [], deferred, missing: [] }
}

/** `is` or `are` for a list of criteria: one criterion takes `is`, two take `are`. */
function isAre(items: readonly string[]): string {
  return items.length === 1 ? 'is' : 'are'
}

/**
 * The verdict as a clause for the card line. One rule with two renderings: this
 * and `verdictSentence` read the same `hnswGateVerdict`, so the card and the
 * coverage sentence cannot disagree about the same run.
 *
 * A deferral is named in both outcomes. A fast run that fails recall was never
 * measured at the gate size either, so the clause carries the deferred
 * percentiles alongside the failure; listing the criteria and stopping at the
 * failure would read as though the latency checks had been evaluated and held,
 * and only `verdictSentence` would disclose that they were not.
 *
 * A deferred pass says so: it names the one criterion that decided the run and
 * the percentiles it postponed. Calling it a flat pass would hide that the run
 * was never measured at the gate size, and "verdict not published" would
 * contradict the publisher, which calls this outcome a pass.
 */
function verdictClause(verdict: HnswGateVerdict): string {
  const deferred = verdict.deferred.length ? `, ${listWords(verdict.deferred)} deferred` : ''
  if (verdict.status === 'fail') return `fails ${listWords(verdict.failed)}${deferred}`
  if (verdict.status === 'unknown') return 'verdict not published'
  return verdict.deferred.length ? `pass on recall${deferred}` : 'pass'
}

/** The verdict as a sentence: the same rule, spelled out for running text. */
function verdictSentence(verdict: HnswGateVerdict): string {
  const until = formatCorpusSize(HNSW_GATE_CORPUS)
  if (verdict.status === 'fail') {
    const failed = `Fails on ${listWords(verdict.failed)}.`
    if (!verdict.deferred.length) return failed
    return `${failed} ${listWords(verdict.deferred)} ${isAre(verdict.deferred)} deferred until a cell reaches ${until}.`
  }
  if (verdict.status === 'unknown') return 'The publisher published no verdict for at least one criterion.'
  if (verdict.deferred.length) {
    return `Passed; ${listWords(verdict.deferred)} ${isAre(verdict.deferred)} deferred until a cell reaches ${until}.`
  }
  return 'All three hold.'
}

/**
 * Compact gate line for a card header: every criterion the publisher applies and
 * the outcome, so no single row can stand for the gate.
 */
export function hnswGateHeadline(cells: readonly ScoredCell[], gate: HnswGateSummary): string {
  const criteria = hnswGateChecks(cells, gate).map(check => check.label).join(' · ')
  return `${criteria} · ${verdictClause(hnswGateVerdict(cells, gate))}`
}

/**
 * The gate in one sentence: every criterion the publisher applies, the value each
 * was measured at, and how the run was decided — including a pass that rests on
 * recall because the 1M cell was never published.
 */
export function hnswGateText(cells: readonly ScoredCell[], gate: HnswGateSummary): string {
  const verdict = hnswGateVerdict(cells, gate)
  const recall = `worst recall ${formatShare(hnswWorstRecall(cells, gate))} against the ${formatShare(gate.recall_floor)} floor`
  if (verdict.deferred.length) {
    return `Gate criteria: ${recall}; ${P95} and ${P99} are not measured, because this run publishes no cell at ${formatCorpusSize(HNSW_GATE_CORPUS)}. ${verdictSentence(verdict)}`
  }
  const cell = hnswGateCell(cells)
  if (!cell) {
    // A gate reported without a cell to quote: name the criterion and the verdict
    // rather than quote values the page does not have.
    return `Gate criteria: ${recall}. ${verdictSentence(verdict)}`
  }
  const latencies = `${P95} ${formatMs(cell.latency_ms_p95)} and ${P99} ${formatMs(cell.latency_ms_p99)} at ${formatCorpusSize(cell.corpus_size)} (the first published cell at or above ${formatCorpusSize(HNSW_GATE_CORPUS)}) against the publisher's latency limits`
  return `Gate criteria: ${recall}, and ${latencies}. ${verdictSentence(verdict)}`
}

/**
 * One line of coverage for the HNSW surfaces: the published sizes in ascending
 * order, the reported gaps, all three criteria the publisher gates, and the
 * verdict the publisher would reach on them.
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
