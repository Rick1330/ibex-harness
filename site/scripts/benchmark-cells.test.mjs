/**
 * The HNSW cell selection is a display contract: a reordered or incomplete
 * `results` array must not move a label onto the wrong corpus, and the gate
 * badge must sit on the cell `benchmarks/memory/publish_cells.py` gated.
 *
 * The gate itself has three criteria — worst recall, p95 at the gate cell, and
 * p99 at the gate cell — because `compute_status` fails a run when recall fails
 * **or** either latency fails. The assertions below fail if the page goes back
 * to naming p95 as "the gate metric".
 *
 * The module under test is TypeScript and holds no imports of the published
 * JSON, so `node --test` strips its types and loads it directly (Node >= 22.18).
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  formatCorpusSize,
  HNSW_GATE_CORPUS,
  hnswCoverage,
  hnswGateCell,
  hnswGateChecks,
  hnswGateHeadline,
  hnswGateText,
  hnswMissingCells,
  hnswSummaryRows,
  hnswWorstRecall,
  largestHnswCell,
  sortHnswCells,
} from '../app/data/benchmark-cells.ts'

/** A published cell: the selection fields, and the values the gate quotes. */
function cell(corpusSize, overrides = {}) {
  return { corpus_size: corpusSize, recall_at_10: 0.99, latency_ms_p95: 10, latency_ms_p99: 20, ...overrides }
}

/** The gate summary of a run that passes all three criteria. */
function passingGate(overrides = {}) {
  return {
    recall_floor: 0.98,
    worst_recall_at_10: 0.986,
    recall_ok: true,
    p95_1m_ok: true,
    p99_1m_ok: true,
    ...overrides,
  }
}

const reordered = () => [cell(1_000_000), cell(10_000), cell(100_000)]
const truncated = () => [cell(10_000), cell(100_000)]

describe('formatCorpusSize', () => {
  it('labels the published profile sizes as 10k, 100k, and 1M', () => {
    assert.equal(formatCorpusSize(10_000), '10k')
    assert.equal(formatCorpusSize(100_000), '100k')
    assert.equal(formatCorpusSize(1_000_000), '1M')
  })

  it('keeps an exact size that is not a whole unit as digits', () => {
    assert.equal(formatCorpusSize(500_000), '500k')
    assert.equal(formatCorpusSize(1_500_000), '1.5M')
    assert.equal(formatCorpusSize(2_000_000), '2M')
  })

  it('never rounds one corpus onto another corpus label', () => {
    assert.equal(formatCorpusSize(1_234_567), '1,234,567')
    assert.notEqual(formatCorpusSize(1_234_567), formatCorpusSize(1_200_000))
  })

  it('prints a dash for a non-finite size', () => {
    assert.equal(formatCorpusSize(Number.NaN), '—')
  })
})

describe('sortHnswCells', () => {
  it('orders reordered cells ascending and leaves the input untouched', () => {
    const cells = reordered()
    assert.deepEqual(sortHnswCells(cells).map(item => item.corpus_size), [10_000, 100_000, 1_000_000])
    assert.deepEqual(cells.map(item => item.corpus_size), [1_000_000, 10_000, 100_000])
  })

  it('returns an empty list for an empty run', () => {
    assert.deepEqual(sortHnswCells([]), [])
  })
})

describe('hnswGateCell', () => {
  it('takes the first cell at or above 1M, as compute_gate_summary does', () => {
    const reorderedCells = reordered()
    assert.equal(hnswGateCell(reorderedCells), reorderedCells[0])

    const aboveGate = [cell(2_000_000), cell(1_000_000)]
    assert.equal(hnswGateCell(aboveGate), aboveGate[0])
  })

  it('returns undefined when no cell reaches the gate', () => {
    assert.equal(hnswGateCell(truncated()), undefined)
  })

  it('returns undefined for an empty run instead of throwing', () => {
    assert.equal(hnswGateCell([]), undefined)
  })
})

describe('largestHnswCell', () => {
  it('finds the largest cell by size, not the last entry', () => {
    assert.equal(largestHnswCell(reordered())?.corpus_size, 1_000_000)
  })

  it('returns undefined for an empty run instead of throwing', () => {
    assert.equal(largestHnswCell([]), undefined)
  })
})

describe('hnswMissingCells', () => {
  it('reports a profile size with no published cell', () => {
    assert.deepEqual(hnswMissingCells(truncated()), [HNSW_GATE_CORPUS])
  })

  it('reports nothing when the profile is complete', () => {
    assert.deepEqual(hnswMissingCells(reordered()), [])
  })
})

describe('hnswWorstRecall', () => {
  it('reads the published worst recall rather than the mean', () => {
    assert.equal(hnswWorstRecall(reordered(), passingGate()), 0.986)
  })

  it('falls back to the minimum cell recall when the summary omits it', () => {
    const cells = [cell(10_000, { recall_at_10: 0.995 }), cell(1_000_000, { recall_at_10: 0.981 })]
    assert.equal(hnswWorstRecall(cells, passingGate({ worst_recall_at_10: undefined })), 0.981)
  })

  it('returns undefined for an empty run', () => {
    assert.equal(hnswWorstRecall([], passingGate({ worst_recall_at_10: undefined })), undefined)
  })
})

describe('hnswGateChecks', () => {
  it('reports the three criteria compute_status applies, in order', () => {
    const checks = hnswGateChecks(reordered(), passingGate())
    assert.deepEqual(checks.map(check => check.criterion), ['recall', 'p95', 'p99'])
    assert.deepEqual(checks.map(check => check.ok), [true, true, true])
  })

  it('derives the recall verdict from the published floor when recall_ok is absent', () => {
    const gate = passingGate({ recall_ok: undefined, worst_recall_at_10: 0.979 })
    const [recall] = hnswGateChecks(reordered(), gate)
    assert.equal(recall?.ok, false)
  })

  it('keeps a latency verdict unknown when the artifact publishes none', () => {
    const gate = passingGate({ p95_1m_ok: undefined, p99_1m_ok: undefined })
    assert.deepEqual(hnswGateChecks(reordered(), gate).map(check => check.ok), [true, undefined, undefined])
  })
})

describe('hnswGateHeadline', () => {
  it('names all three criteria and the outcome in one line', () => {
    assert.equal(hnswGateHeadline(reordered(), passingGate()), 'worst recall · p95 · p99 · pass')
  })

  it('names the failed criterion instead of claiming a pass', () => {
    assert.equal(
      hnswGateHeadline(reordered(), passingGate({ p99_1m_ok: false })),
      'worst recall · p95 · p99 · fails p99',
    )
  })

  it('does not claim a verdict the artifact does not publish', () => {
    assert.equal(
      hnswGateHeadline(reordered(), passingGate({ p95_1m_ok: undefined })),
      'worst recall · p95 · p99 · verdict not published',
    )
  })
})

describe('hnswGateText', () => {
  it('names recall, p95, and p99 together and says all three hold', () => {
    const text = hnswGateText(reordered(), passingGate())
    assert.match(text, /^Gate criteria: worst recall 98\.6% against the 98\.0% floor/)
    assert.match(text, /p95 10\.0 ms and p99 20\.0 ms at 1M/)
    assert.match(text, /All three hold\.$/)
  })

  it('does not reduce the gate to p95 alone', () => {
    const text = hnswGateText(reordered(), passingGate())
    assert.doesNotMatch(text, /Gate metric: p95/)
    assert.doesNotMatch(text, /p95 at 1M, the first published cell/)
  })

  it('fails on p99 when p95 is inside its limit and p99 is outside', () => {
    const gate = passingGate({ p99_1m_ok: false })
    const text = hnswGateText(reordered(), gate)
    assert.match(text, /Fails on p99\.$/)
    assert.doesNotMatch(text, /All three hold/)
  })

  it('fails on p95 when only p95 is outside its limit', () => {
    const gate = passingGate({ p95_1m_ok: false })
    assert.match(hnswGateText(reordered(), gate), /Fails on p95\.$/)
  })

  it('fails on both latencies when both are outside their limits', () => {
    const gate = passingGate({ p95_1m_ok: false, p99_1m_ok: false })
    assert.match(hnswGateText(reordered(), gate), /Fails on p95 and p99\.$/)
  })

  it('fails on worst recall when the floor is not met, even if latencies hold', () => {
    const gate = passingGate({ recall_ok: false, worst_recall_at_10: 0.979 })
    const text = hnswGateText(reordered(), gate)
    assert.match(text, /worst recall 97\.9% against the 98\.0% floor/)
    assert.match(text, /Fails on worst recall\.$/)
  })

  it('says p95 and p99 are unmeasured when no cell reaches the gate', () => {
    const gate = passingGate({ p95_1m_ok: undefined, p99_1m_ok: undefined })
    const text = hnswGateText(truncated(), gate)
    assert.match(text, /Gate criteria: worst recall 98\.6% against the 98\.0% floor/)
    assert.match(text, /p95 and p99 are not measured, because no published cell reaches 1M\./)
    assert.doesNotMatch(text, /Fails|All three hold/)
  })

  it('does not claim a pass when the artifact publishes no verdict', () => {
    const gate = passingGate({ p95_1m_ok: undefined })
    const text = hnswGateText(reordered(), gate)
    assert.match(text, /no verdict for at least one criterion/)
    assert.doesNotMatch(text, /All three hold/)
  })
})

describe('hnswCoverage', () => {
  it('labels each cell by its own size when the data is reordered', () => {
    const coverage = hnswCoverage(reordered(), passingGate())
    assert.match(coverage, /Published cells: 10k, 100k, 1M\./)
    assert.doesNotMatch(coverage, /Not reported/)
    assert.match(coverage, /Gate criteria: worst recall 98\.6% against the 98\.0% floor, and p95 10\.0 ms and p99 20\.0 ms at 1M/)
  })

  it('says the gate cell is absent rather than claiming 1M', () => {
    const coverage = hnswCoverage(truncated(), passingGate({ p95_1m_ok: undefined, p99_1m_ok: undefined }))
    assert.match(coverage, /Published cells: 10k, 100k\./)
    assert.match(coverage, /Not reported: 1M\./)
    assert.match(coverage, /p95 and p99 are not measured/)
    assert.doesNotMatch(coverage, /p95 10\.0 ms and p99 20\.0 ms at 1M/)
  })

  it('names no cell for an empty run', () => {
    assert.match(hnswCoverage([], passingGate()), /No HNSW cells are published/)
  })
})

describe('hnswSummaryRows', () => {
  it('badges exactly the gate cell when the data is reordered', () => {
    const rows = hnswSummaryRows(reordered())
    assert.deepEqual(rows.map(row => row.label), ['p95 at 10k', 'p95 at 100k', 'p95 at 1M'])
    assert.deepEqual(rows.map(row => row.gate), [false, false, true])
  })

  it('shows p99 on every row so the gate p99 cannot be invisible', () => {
    const rows = hnswSummaryRows(reordered())
    assert.deepEqual(rows.map(row => row.note), ['p99 20.0 ms', 'p99 20.0 ms', 'p99 20.0 ms · gate metrics'])
    assert.deepEqual(rows.map(row => row.value), ['10.0 ms', '10.0 ms', '10.0 ms'])
  })

  it('badges the first cell above the gate when 1M is not published', () => {
    const rows = hnswSummaryRows([cell(2_000_000, { latency_ms_p99: 140 }), cell(10_000)])
    assert.deepEqual(rows.map(row => row.label), ['p95 at 10k', 'p95 at 2M'])
    assert.deepEqual(rows.map(row => row.gate), [false, true])
    assert.equal(rows[1]?.note, 'p99 140.0 ms · gate metrics')
  })

  it('badges no row when no cell reaches the gate', () => {
    assert.deepEqual(hnswSummaryRows(truncated()).map(row => row.gate), [false, false])
  })

  it('badges nothing for an empty run', () => {
    assert.deepEqual(hnswSummaryRows([]), [])
  })
})
