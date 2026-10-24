import proxyData from '../../public/benchmarks/benchmark-data.json'
import hnswData from '../../public/benchmarks/hnsw-benchmark-data.json'
import rankingData from '../../public/benchmarks/ranking-quality-benchmark-data.json'
import writeData from '../../public/benchmarks/write-pipeline-benchmark-data.json'
import extractionData from '../../public/benchmarks/extraction-quality-benchmark-data.json'

function newest<T>(runs: T[], name: string): T {
  const first = runs[0]
  if (!first) throw new Error(`No published ${name} benchmark runs`)
  return first
}

export const proxyRuns = proxyData.runs
export const latestProxy = newest(proxyRuns, 'proxy')
export const hnswRuns = hnswData.runs
export const latestHnsw = newest(hnswRuns, 'HNSW')
export const rankingRuns = rankingData.runs
export const latestRanking = newest(rankingRuns, 'ranking')
export const writeRuns = writeData.runs
export const latestWrite = newest(writeRuns, 'write-pipeline')
export const extractionRuns = extractionData.runs
export const latestExtraction = newest(extractionRuns, 'extraction')

export const benchmarkMeta = {
  proxy: {
    title: 'Proxy overhead',
    file: 'benchmark-data.json',
    description: 'Warm-path proxy benchmark. The gate is mean-based; it is not a p99 SLO measurement.',
  },
  hnsw: {
    title: 'HNSW recall and latency',
    file: 'hnsw-benchmark-data.json',
    description: 'pgvector HNSW recall and search latency against a local corpus.',
  },
  ranking: {
    title: 'Ranking quality',
    file: 'ranking-quality-benchmark-data.json',
    description: 'Gold-set precision, recall, MRR, and expected-order checks.',
  },
  write: {
    title: 'Write pipeline',
    file: 'write-pipeline-benchmark-data.json',
    description: 'End-to-end memory write latency at p50, p95, and p99.',
  },
  extraction: {
    title: 'Extraction quality',
    file: 'extraction-quality-benchmark-data.json',
    description: 'Cassette-mode extraction quality against the v1 gold set.',
  },
} as const

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value)
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(value))
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${formatNumber(value * 100, digits)}%`
}
