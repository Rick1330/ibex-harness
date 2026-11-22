/**
 * The HNSW cell selection is a display contract: a reordered or incomplete
 * `results` array must not move a label onto the wrong corpus, and the gate
 * badge must sit on the cell `benchmarks/memory/publish_cells.py` gated.
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
  hnswMissingCells,
  hnswSummaryRows,
  largestHnswCell,
  sortHnswCells,
} from '../app/data/benchmark-cells.ts'

/** A published cell carrying only the field the selection rules read. */
function cell(corpusSize) {
  return { corpus_size: corpusSize }
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

describe('hnswCoverage', () => {
  it('labels each cell by its own size when the data is reordered', () => {
    const coverage = hnswCoverage(reordered())
    assert.match(coverage, /Published cells: 10k, 100k, 1M\./)
    assert.match(coverage, /Gate metric: p95 at 1M, the first published cell at or above 1M\./)
    assert.doesNotMatch(coverage, /Not reported/)
  })

  it('says the gate cell is absent rather than claiming 1M', () => {
    const coverage = hnswCoverage(truncated())
    assert.match(coverage, /Published cells: 10k, 100k\./)
    assert.match(coverage, /Not reported: 1M\./)
    assert.match(coverage, /Gate metric: none/)
    assert.doesNotMatch(coverage, /p95 at 1M/)
  })

  it('names no cell for an empty run', () => {
    assert.match(hnswCoverage([]), /No HNSW cells are published/)
  })
})

describe('hnswSummaryRows', () => {
  it('badges exactly the gate cell when the data is reordered', () => {
    const rows = hnswSummaryRows(reordered())
    assert.deepEqual(rows.map(row => row.label), ['p95 at 10k', 'p95 at 100k', 'p95 at 1M'])
    assert.deepEqual(rows.map(row => row.note), [undefined, undefined, 'gate metric'])
  })

  it('badges the first cell above the gate when 1M is not published', () => {
    const rows = hnswSummaryRows([cell(2_000_000), cell(10_000)])
    assert.deepEqual(rows.map(row => row.label), ['p95 at 10k', 'p95 at 2M'])
    assert.deepEqual(rows.map(row => row.note), [undefined, 'gate metric'])
  })

  it('badges no row when no cell reaches the gate', () => {
    assert.deepEqual(hnswSummaryRows(truncated()).map(row => row.note), [undefined, undefined])
  })

  it('badges nothing for an empty run', () => {
    assert.deepEqual(hnswSummaryRows([]), [])
  })
})
