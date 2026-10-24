<script setup lang="ts">
import {
  benchmarkMeta,
  formatDate,
  formatNumber,
  formatPercent,
  latestExtraction,
  latestHnsw,
  latestProxy,
  latestRanking,
  latestWrite,
  extractionRuns,
  hnswRuns,
  proxyRuns,
  rankingRuns,
  writeRuns,
} from '~/data/benchmarks'

useSeoMeta({
  title: 'Benchmarks',
  description: 'Published local benchmark data for the IBEX Harness proxy, memory retrieval, ranking, write pipeline, and extraction quality.',
  ogTitle: 'IBEX Harness benchmarks',
  ogDescription: 'Five measurement suites with workloads, gates, environments, and limitations. No hosted p99 claim.',
})

const totalRuns = computed(() => proxyRuns.length + hnswRuns.length + rankingRuns.length + writeRuns.length + extractionRuns.length)

const proxyHistory = computed(() => [...proxyRuns].reverse())
const proxyWindow = computed(() => proxyHistory.value.slice(-32))
const proxyLabels = computed(() => proxyHistory.value.map(run => formatDate(run.timestamp).replace(/, \d{4}$/, '')))
const proxyThroughput = computed(() => latestProxy.k6.throughput_series.map(point => point.req_per_s))
const proxyThroughputLabels = computed(() => latestProxy.k6.throughput_series.map(point => `${point.t_s}s`))

const proxyPercentileSeries = computed(() => [
  { label: 'p50', values: proxyWindow.value.map(run => run.k6.p50_ms), color: 'var(--chart-lime)', suffix: ' ms', digits: 3 },
  { label: 'p95', values: proxyWindow.value.map(run => run.k6.p95_ms), color: 'var(--chart-blue)', suffix: ' ms', digits: 3 },
  { label: 'p99', values: proxyWindow.value.map(run => run.k6.p99_ms), color: 'var(--chart-pink)', suffix: ' ms', digits: 3 },
])

const proxyPercentileLegend = computed(() => proxyPercentiles.value.slice(0, 3).map(item => ({
  label: item.label,
  value: `${formatNumber(item.value, 3)} ms`,
  color: item.color,
})))

const proxyThroughputSeries = computed(() => [
  { label: 'Throughput', values: proxyThroughput.value, color: 'var(--chart-lime)', suffix: ' req/s', digits: 0 },
])

const proxyThroughputLegend = computed(() => [
  { label: 'Mean across run', value: `${formatNumber(latestProxy.k6.req_per_s, 0)} req/s`, color: 'var(--chart-lime)' },
])

const proxyPercentiles = computed(() => [
  { label: 'p50', value: latestProxy.k6.p50_ms, display: `${formatNumber(latestProxy.k6.p50_ms, 3)} ms`, note: 'median', color: 'var(--chart-lime)' },
  { label: 'p95', value: latestProxy.k6.p95_ms, display: `${formatNumber(latestProxy.k6.p95_ms, 3)} ms`, color: 'var(--chart-blue)' },
  { label: 'p99', value: latestProxy.k6.p99_ms, display: `${formatNumber(latestProxy.k6.p99_ms, 3)} ms`, color: 'var(--chart-pink)' },
  { label: 'p999', value: latestProxy.k6.p999_ms, display: `${formatNumber(latestProxy.k6.p999_ms, 3)} ms`, note: 'extreme tail', color: 'var(--chart-violet)' },
])

const stageRows = computed(() => [
  { label: 'Auth LRU', value: latestProxy.stages.auth_lru_p50_ms * 1000, display: micro(latestProxy.stages.auth_lru_p50_ms) },
  { label: 'Auth gRPC', value: latestProxy.stages.auth_grpc_p50_ms * 1000, display: micro(latestProxy.stages.auth_grpc_p50_ms) },
  { label: 'Rate limit', value: latestProxy.stages.rate_limit_p50_ms * 1000, display: micro(latestProxy.stages.rate_limit_p50_ms) },
  { label: 'Directive', value: latestProxy.stages.directive_resolve_p50_ms * 1000, display: micro(latestProxy.stages.directive_resolve_p50_ms) },
  { label: 'Prompt', value: latestProxy.stages.prompt_inject_p50_ms * 1000, display: micro(latestProxy.stages.prompt_inject_p50_ms) },
])

const stageTotal = computed(() => ({
  label: 'Total',
  value: latestProxy.stages.total_overhead_p50_ms * 1000,
  display: micro(latestProxy.stages.total_overhead_p50_ms),
}))

const goBenchmarkLabels: Record<string, string> = {
  BenchmarkStageAuth: 'Stage auth',
  BenchmarkStageRateLimit: 'Stage rate limit',
  BenchmarkStageDirectiveResolve: 'Stage directive',
  BenchmarkStagePromptInject: 'Stage prompt',
  BenchmarkProxyOverhead: 'Proxy overhead',
  BenchmarkProxyChatOverhead: 'Chat overhead',
  BenchmarkProxyChatOverheadParallel: 'Chat overhead, parallel',
  BenchmarkProxyChatOverheadWithAssemble: 'Chat overhead + assemble',
  BenchmarkProxyHealth: 'Health',
}

const goBenchmarks = computed(() => Object.entries(latestProxy.go_benchmarks).map(([name, value]) => ({
  name: name.replace('Benchmark', ''),
  label: goBenchmarkLabels[name] ?? name.replace('Benchmark', ''),
  family: name.startsWith('BenchmarkStage') ? 'Stage path' : 'Proxy-level path',
  ns: value.ns_per_op,
  ms: value.ns_per_op / 1_000_000,
  allocs: value.allocs_per_op,
  bytes: value.bytes_per_op,
  samples: value.samples,
  ciLow: value.ci_95_low,
  ciHigh: value.ci_95_high,
  low: value.ci_95_low / 1_000_000,
  high: value.ci_95_high / 1_000_000,
})))

const goBenchItems = computed(() => [...goBenchmarks.value]
  .sort((a, b) => b.ns - a.ns)
  .map(row => ({
    label: row.label,
    value: row.ns,
    display: `${formatNumber(row.ns, 0)} ns`,
    note: `${formatNumber(row.ns / 1000, 1)} µs · ${formatNumber(row.allocs, 0)} allocs`,
    color: row.family === 'Stage path' ? 'var(--chart-lime)' : 'var(--chart-blue)',
    low: row.ciLow,
    high: row.ciHigh,
  })))

const goLegend = computed(() => {
  const range = (family: string) => {
    const rows = goBenchmarks.value.filter(row => row.family === family)
    if (!rows.length) return '—'
    const min = Math.min(...rows.map(row => row.ns))
    const max = Math.max(...rows.map(row => row.ns))
    return `${compactNs(min)} – ${compactNs(max)}`
  }
  return [
    { label: 'Stage path', value: range('Stage path'), color: 'var(--chart-lime)' },
    { label: 'Proxy-level path', value: range('Proxy-level path'), color: 'var(--chart-blue)' },
  ]
})

const hnswRows = computed(() => latestHnsw.results || [])

const rankingRows = computed(() => [
  { label: 'Precision@5', value: latestRanking.metrics.precision_at_5 },
  { label: 'Recall@10', value: latestRanking.metrics.recall_at_10 },
  { label: 'MRR', value: latestRanking.metrics.mrr },
  { label: 'Order match', value: latestRanking.metrics.expected_order_match },
  { label: 'Top category', value: latestRanking.metrics.top_category_accuracy },
])

const rankingAtCeiling = computed(() => rankingRows.value.filter(row => row.value === 1).length)

const rankingGate = computed(() => {
  const checks = latestRanking.gate_summary.checks
  return {
    passed: checks.filter(check => check.ok).length,
    total: checks.length,
  }
})

const writeHistory = computed(() => [...writeRuns].reverse())
const writeLabels = computed(() => writeHistory.value.map(run => formatDate(run.timestamp).replace(/, \d{4}$/, '')))
const writeRegression = computed(() => {
  const check = latestWrite.gate_summary.checks.find(item => item.name.includes('regression'))
  return check ? check.value : null
})

const writeSeries = computed(() => [
  { label: 'p50', values: writeHistory.value.map(run => run.metrics.latency_ms_p50), color: 'var(--chart-lime)', suffix: ' ms', digits: 1 },
  { label: 'p95', values: writeHistory.value.map(run => run.metrics.latency_ms_p95), color: 'var(--chart-blue)', suffix: ' ms', digits: 1 },
  { label: 'p99', values: writeHistory.value.map(run => run.metrics.latency_ms_p99), color: 'var(--chart-pink)', suffix: ' ms', digits: 1 },
])

const writeLegend = computed(() => writePercentiles.value.map(item => ({
  label: item.label,
  value: item.display,
  color: item.color,
})))

const writePercentiles = computed(() => [
  { label: 'p50', value: latestWrite.metrics.latency_ms_p50, display: `${formatNumber(latestWrite.metrics.latency_ms_p50, 1)} ms`, note: 'median', color: 'var(--chart-lime)' },
  { label: 'p95', value: latestWrite.metrics.latency_ms_p95, display: `${formatNumber(latestWrite.metrics.latency_ms_p95, 1)} ms`, note: 'gate 200 ms', color: 'var(--chart-blue)' },
  { label: 'p99', value: latestWrite.metrics.latency_ms_p99, display: `${formatNumber(latestWrite.metrics.latency_ms_p99, 1)} ms`, note: 'tail', color: 'var(--chart-pink)' },
])

const hnswLabels = computed(() => hnswRows.value.map(row => `${formatNumber(row.corpus_size / 1000, 0)}k`))

const hnswSeries = computed(() => [
  { label: 'p50', values: hnswRows.value.map(row => row.latency_ms_p50), color: 'var(--chart-lime)', suffix: ' ms', digits: 1 },
  { label: 'p95', values: hnswRows.value.map(row => row.latency_ms_p95), color: 'var(--chart-blue)', suffix: ' ms', digits: 1 },
  { label: 'p99', values: hnswRows.value.map(row => row.latency_ms_p99), color: 'var(--chart-pink)', suffix: ' ms', digits: 1 },
])

const hnswLegend = computed(() => {
  const row = hnswRows.value[hnswRows.value.length - 1]
  if (!row) return []
  return [
    { label: 'p50 at 100k', value: `${formatNumber(row.latency_ms_p50, 1)} ms`, color: 'var(--chart-lime)' },
    { label: 'p95 at 100k', value: `${formatNumber(row.latency_ms_p95, 1)} ms`, color: 'var(--chart-blue)' },
    { label: 'p99 at 100k', value: `${formatNumber(row.latency_ms_p99, 1)} ms`, color: 'var(--chart-pink)' },
  ]
})

const hnswRecallRows = computed(() => hnswRows.value.map(row => ({
  label: `${formatNumber(row.corpus_size / 1000, 0)}k rows`,
  value: row.recall_at_10,
  display: formatPercent(row.recall_at_10),
})))

const hnswCi = computed(() => hnswRows.value.map(row => ({
  label: `${formatNumber(row.corpus_size / 1000, 0)}k`,
  value: `${formatNumber(row.latency_ms_p95_ci_low, 1)}–${formatNumber(row.latency_ms_p95_ci_high, 1)} ms`,
})))

const extractionCategories = ['factual', 'preference', 'behavioral', 'episodic', 'procedural'] as const
const extractionRows = computed(() => extractionCategories.map(category => ({
  name: category.charAt(0).toUpperCase() + category.slice(1),
  precision: latestExtraction.metrics[`precision_${category}`],
  recall: latestExtraction.metrics[`recall_${category}`],
})))

const extractionMacro = computed(() => [
  { label: 'Macro precision', value: latestExtraction.metrics.precision_macro },
  { label: 'Macro recall', value: latestExtraction.metrics.recall_macro },
  { label: 'Category accuracy', value: latestExtraction.metrics.category_assignment_accuracy },
  { label: 'Temporal accuracy', value: latestExtraction.metrics.temporal_field_accuracy },
])

// Runs are published newest-first and failed runs are kept, so the latest run
// can be a failing one; every gate summary on the page must derive from data.
const extractionGate = computed(() => {
  const checks = latestExtraction.gate_summary.checks
  return {
    passed: checks.filter(check => check.ok).length,
    total: checks.length,
  }
})

const extractionLegend = computed(() => [
  { label: 'Macro precision', value: formatPercent(latestExtraction.metrics.precision_macro), color: 'var(--chart-lime)' },
  { label: 'Macro recall', value: formatPercent(latestExtraction.metrics.recall_macro), color: 'var(--chart-blue)' },
])

const suites = computed(() => [
  {
    index: '01',
    title: 'Proxy overhead',
    shortTitle: 'Proxy',
    icon: 'i-lucide-gauge',
    detail: 'Warm-path auth, rate limiting, directive resolution, and prompt injection.',
    metric: `${formatNumber(latestProxy.k6.p50_ms, 3)} ms`,
    metricLabel: 'p50',
    runs: proxyRuns.length,
    tag: 'not an SLO',
    href: '#proxy',
  },
  {
    index: '02',
    title: 'Memory retrieval',
    shortTitle: 'Memory',
    icon: 'i-lucide-database',
    detail: 'pgvector HNSW recall and wall-clock search latency across corpus sizes.',
    metric: formatPercent(latestHnsw.mean_recall_at_10),
    metricLabel: 'mean recall@10',
    runs: hnswRuns.length,
    tag: `p95 ${formatNumber(hnswRows.value[1]?.latency_ms_p95, 1)} ms`,
    href: '#retrieval',
  },
  {
    index: '03',
    title: 'Ranking quality',
    shortTitle: 'Ranking',
    icon: 'i-lucide-list-checks',
    detail: 'Gold-set precision, recall, reciprocal rank, and ordering checks.',
    metric: `${rankingAtCeiling.value} / ${rankingRows.value.length}`,
    metricLabel: 'metrics at 1.0',
    runs: rankingRuns.length,
    tag: 'gold set v1',
    href: '#ranking',
  },
  {
    index: '04',
    title: 'Write pipeline',
    shortTitle: 'Writes',
    icon: 'i-lucide-arrow-down-to-line',
    detail: 'End-to-end memory write latency from request through persistence.',
    metric: `${formatNumber(latestWrite.metrics.latency_ms_p95, 1)} ms`,
    metricLabel: 'p95',
    runs: writeRuns.length,
    tag: 'gate 200 ms',
    href: '#writes',
  },
  {
    index: '05',
    title: 'Extraction quality',
    shortTitle: 'Extraction',
    icon: 'i-lucide-scan-text',
    detail: 'Structured extraction against a 125-conversation gold set in cassette mode.',
    metric: `${extractionGate.value.passed} / ${extractionGate.value.total}`,
    metricLabel: 'gate checks pass',
    runs: extractionRuns.length,
    tag: 'cassette',
    href: '#extraction',
  },
])

const navSuites = computed(() => suites.value.map(({ index, title, shortTitle, icon, metric, metricLabel, runs, href }) => ({
  index,
  title,
  shortTitle,
  icon,
  metric,
  metricLabel,
  runs,
  href,
})))

const jsonFiles = [
  { label: 'Proxy overhead', href: '/benchmarks/benchmark-data.json', meta: benchmarkMeta.proxy, runs: proxyRuns.length, updated: latestProxy.timestamp },
  { label: 'HNSW recall / latency', href: '/benchmarks/hnsw-benchmark-data.json', meta: benchmarkMeta.hnsw, runs: hnswRuns.length, updated: latestHnsw.timestamp },
  { label: 'Ranking quality', href: '/benchmarks/ranking-quality-benchmark-data.json', meta: benchmarkMeta.ranking, runs: rankingRuns.length, updated: latestRanking.timestamp },
  { label: 'Write pipeline', href: '/benchmarks/write-pipeline-benchmark-data.json', meta: benchmarkMeta.write, runs: writeRuns.length, updated: latestWrite.timestamp },
  { label: 'Extraction quality', href: '/benchmarks/extraction-quality-benchmark-data.json', meta: benchmarkMeta.extraction, runs: extractionRuns.length, updated: latestExtraction.timestamp },
]

const mobileNavItems = computed(() => [
  ...navSuites.value,
  { index: '06', title: 'Method', shortTitle: 'Method', icon: 'i-lucide-book-open', href: '#method' },
  { index: '07', title: 'Raw data', shortTitle: 'Data', icon: 'i-lucide-braces', href: '#raw-data' },
])

const isCompact = ref(false)

function updateViewport() {
  isCompact.value = window.innerWidth < 640
}

const sectionIds = ['proxy', 'retrieval', 'ranking', 'writes', 'extraction', 'method', 'raw-data']
const activeSection = ref('proxy')
const mobileNav = ref<HTMLElement | null>(null)

interface ModalSummaryItem {
  label: string
  value: string
  note?: string
  color?: string
}

interface ModalSeries {
  label: string
  values: number[]
  color?: string
  suffix?: string
  digits?: number
}

interface ModalMeterItem {
  label: string
  value: number
  display: string
  note?: string
  color?: string
}

interface ModalComparisonMetric {
  label: string
  current: string
  previous: string
  change: string
  tone: 'better' | 'worse' | 'same'
}

interface GraphModalState {
  open: boolean
  eyebrow: string
  title: string
  description: string
  sourceHref: string
  chartKind: 'line' | 'bar' | 'meter' | 'list'
  lineSeries: ModalSeries[]
  lineLabels: string[]
  threshold?: number
  thresholdLabel: string
  barLabels: string[]
  barSeries: ModalSeries[]
  barYTicks: number
  meterItems: ModalMeterItem[]
  meterThreshold?: { value: number, label: string }
  listItems: { label: string, value: number, display: string, note?: string, color?: string, low?: number, high?: number }[]
  meterTotal?: ModalMeterItem
  summary: ModalSummaryItem[]
  tableColumns: string[]
  tableRows: string[][]
  tableNote: string
  selectable: boolean
  activeIndex: number | null
  selectionLabel: string
}

type ModalKind =
  | 'proxy-latency'
  | 'proxy-throughput'
  | 'proxy-stages'
  | 'go-benchmarks'
  | 'hnsw-latency'
  | 'hnsw-recall'
  | 'hnsw-method'
  | 'ranking'
  | 'write-history'
  | 'write-latest'
  | 'write-gate'
  | 'extraction-categories'
  | 'extraction-summary'

function blankModal(): GraphModalState {
  return {
    open: true,
    eyebrow: '',
    title: '',
    description: '',
    sourceHref: '',
    chartKind: 'line',
    lineSeries: [],
    lineLabels: [],
    threshold: undefined,
    thresholdLabel: '',
    barLabels: [],
    barSeries: [],
    barYTicks: 4,
    meterItems: [],
    meterThreshold: undefined,
    meterTotal: undefined,
    listItems: [],
    summary: [],
    tableColumns: [],
    tableRows: [],
    tableNote: '',
    selectable: false,
    activeIndex: null,
    selectionLabel: '',
  }
}

const modalKind = ref<ModalKind | null>(null)
const pinnedRow = ref(0)
const hoverRow = ref<number | null>(null)
const activeModalRow = computed(() => hoverRow.value ?? pinnedRow.value)
const graphModal = computed<GraphModalState>(() => modalKind.value
  ? buildModal(modalKind.value, activeModalRow.value)
  : { ...blankModal(), open: false })

function openGraph(kind: ModalKind, row = 0) {
  modalKind.value = kind
  pinnedRow.value = row
  hoverRow.value = null
}

function closeGraph() {
  modalKind.value = null
  hoverRow.value = null
}

function previewGraphRow(row: number | null) {
  hoverRow.value = row
}

function selectGraphRow(row: number) {
  pinnedRow.value = row
  hoverRow.value = null
}

function percentChange(current: number, previous: number | undefined | null) {
  if (previous === null || previous === undefined || previous === 0) return null
  return ((current - previous) / previous) * 100
}

function signedPercent(value: number | null) {
  if (value === null || Number.isNaN(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${formatNumber(value, 1)}%`
}

function compareMetric(
  label: string,
  current: number,
  previous: number | undefined,
  options: { digits?: number, unit?: string, higherIsBetter?: boolean } = {},
): ModalComparisonMetric {
  const { digits = 1, unit = '', higherIsBetter = false } = options
  const change = percentChange(current, previous)
  const tone: ModalComparisonMetric['tone'] = change === null || Math.abs(change) < 0.0001
    ? 'same'
    : (higherIsBetter ? change > 0 : change < 0)
        ? 'better'
        : 'worse'
  return {
    label,
    current: `${formatNumber(current, digits)}${unit}`,
    previous: previous === undefined ? '—' : `${formatNumber(previous, digits)}${unit}`,
    change: change === null ? '—' : `${signedPercent(change)}${tone === 'same' ? '' : tone === 'better' ? ' better' : ' worse'}`,
    tone,
  }
}

function summaryWith(
  items: { label: string, value: string, note?: string, color?: string }[],
  metrics: Record<string, ModalComparisonMetric>,
): ModalSummaryItem[] {
  return items.map((item) => {
    const metric = metrics[item.label]
    if (!metric) return item
    return { ...item, previous: metric.previous, change: metric.change, tone: metric.tone }
  })
}

function writePercentilesFor(run: typeof latestWrite): ModalMeterItem[] {
  return [
    { label: 'p50', value: run.metrics.latency_ms_p50, display: `${formatNumber(run.metrics.latency_ms_p50, 1)} ms`, note: 'median', color: 'var(--chart-lime)' },
    { label: 'p95', value: run.metrics.latency_ms_p95, display: `${formatNumber(run.metrics.latency_ms_p95, 1)} ms`, note: 'gate 200 ms', color: 'var(--chart-blue)' },
    { label: 'p99', value: run.metrics.latency_ms_p99, display: `${formatNumber(run.metrics.latency_ms_p99, 1)} ms`, note: 'tail', color: 'var(--chart-pink)' },
  ]
}

const proxyModalLabels = computed(() => proxyHistory.value.map(run => formatDate(run.timestamp).replace(/, \d{4}$/, '')))
const writeModalLabels = computed(() => writeHistory.value.map(run => formatDate(run.timestamp).replace(/, \d{4}$/, '')))

const modalBuilders: Record<ModalKind, (row: number) => GraphModalState> = {
  'proxy-latency': proxyLatencyModal,
  'proxy-throughput': proxyThroughputModal,
  'proxy-stages': () => proxyStagesModal(),
  'go-benchmarks': () => goBenchmarksModal(),
  'hnsw-latency': () => hnswModal('latency'),
  'hnsw-recall': () => hnswModal('recall'),
  'hnsw-method': () => hnswModal('method'),
  ranking: rankingModal,
  'write-history': row => writeModal('history', row),
  'write-latest': row => writeModal('latest', row),
  'write-gate': row => writeModal('gate', row),
  'extraction-categories': row => extractionModal('categories', row),
  'extraction-summary': row => extractionModal('summary', row),
}

function buildModal(kind: ModalKind, row: number): GraphModalState {
  return modalBuilders[kind](row)
}

function proxyLatencyModal(row: number): GraphModalState {
  const run = proxyRuns[row] ?? latestProxy
  const older = proxyRuns[row + 1]
  const k6 = run.k6
  return {
    ...blankModal(),
    eyebrow: '01 / Proxy overhead',
    title: 'Proxy latency history',
    description: 'Every published local k6 run, oldest to newest. Provider time is excluded. Hover to preview a run; click to pin it.',
    sourceHref: run.run_url,
    chartKind: 'line',
    lineSeries: [
      { label: 'p50', values: proxyHistory.value.map(item => item.k6.p50_ms), color: 'var(--chart-lime)', suffix: ' ms', digits: 3 },
      { label: 'p95', values: proxyHistory.value.map(item => item.k6.p95_ms), color: 'var(--chart-blue)', suffix: ' ms', digits: 3 },
      { label: 'p99', values: proxyHistory.value.map(item => item.k6.p99_ms), color: 'var(--chart-pink)', suffix: ' ms', digits: 3 },
      { label: 'p999', values: proxyHistory.value.map(item => item.k6.p999_ms), color: 'var(--chart-violet)', suffix: ' ms', digits: 3 },
    ],
    lineLabels: proxyModalLabels.value,
    selectable: true,
    activeIndex: proxyRuns.length - 1 - row,
    selectionLabel: `Run ${run.run_number} · ${formatDate(run.timestamp)}`,
    summary: summaryWith([
      { label: 'p50', value: `${formatNumber(k6.p50_ms, 3)} ms`, note: 'median', color: 'var(--chart-lime)' },
      { label: 'p95', value: `${formatNumber(k6.p95_ms, 3)} ms`, note: 'warm path', color: 'var(--chart-blue)' },
      { label: 'p99', value: `${formatNumber(k6.p99_ms, 3)} ms`, note: 'tail', color: 'var(--chart-pink)' },
      { label: 'p999', value: `${formatNumber(k6.p999_ms, 3)} ms`, note: 'extreme tail', color: 'var(--chart-violet)' },
    ], {
      p50: compareMetric('p50', k6.p50_ms, older?.k6.p50_ms, { digits: 3, unit: ' ms' }),
      p95: compareMetric('p95', k6.p95_ms, older?.k6.p95_ms, { digits: 3, unit: ' ms' }),
      p99: compareMetric('p99', k6.p99_ms, older?.k6.p99_ms, { digits: 3, unit: ' ms' }),
      p999: compareMetric('p999', k6.p999_ms, older?.k6.p999_ms, { digits: 3, unit: ' ms' }),
    }),
    tableColumns: ['Run', 'Commit', 'Date', 'p50', 'p95', 'p99', 'Req/s', 'Δ p99'],
    tableRows: proxyRuns.map((item, index) => {
      const previousRun = proxyRuns[index + 1]
      return [
        String(item.run_number),
        item.short_sha,
        formatDate(item.timestamp),
        `${formatNumber(item.k6.p50_ms, 3)} ms`,
        `${formatNumber(item.k6.p95_ms, 3)} ms`,
        `${formatNumber(item.k6.p99_ms, 3)} ms`,
        formatNumber(item.k6.req_per_s, 0),
        signedPercent(percentChange(item.k6.p99_ms, previousRun?.k6.p99_ms)),
      ]
    }),
    tableNote: 'Newest first. Δ compares p99 with the next-older published run.',
  }
}

function proxyThroughputModal(row: number): GraphModalState {
  const run = proxyRuns[row] ?? latestProxy
  const older = proxyRuns[row + 1]
  const k6 = run.k6
  return {
    ...blankModal(),
    eyebrow: '01 / Proxy overhead',
    title: 'Throughput history',
    description: 'Mean request rate for each published proxy run. Provider latency is excluded from the warm-path measurement. Hover to preview a run; click to pin it.',
    sourceHref: run.run_url,
    chartKind: 'line',
    lineSeries: [
      { label: 'Throughput', values: proxyHistory.value.map(item => item.k6.req_per_s), color: 'var(--chart-lime)', suffix: ' req/s', digits: 0 },
    ],
    lineLabels: proxyModalLabels.value,
    selectable: true,
    activeIndex: proxyRuns.length - 1 - row,
    selectionLabel: `Run ${run.run_number} · ${formatDate(run.timestamp)}`,
    summary: summaryWith([
      { label: 'Mean', value: `${formatNumber(k6.req_per_s, 0)} req/s`, note: 'throughput', color: 'var(--chart-lime)' },
      { label: 'p50', value: `${formatNumber(k6.p50_ms, 3)} ms`, note: 'median', color: 'var(--chart-blue)' },
      { label: 'p99', value: `${formatNumber(k6.p99_ms, 3)} ms`, note: 'tail', color: 'var(--chart-pink)' },
      { label: 'Errors', value: formatPercent(k6.error_rate), note: k6.error_rate === 0 ? 'no failures' : 'failed requests' },
    ], {
      Mean: compareMetric('Mean', k6.req_per_s, older?.k6.req_per_s, { digits: 0, unit: ' req/s', higherIsBetter: true }),
      p50: compareMetric('p50', k6.p50_ms, older?.k6.p50_ms, { digits: 3, unit: ' ms' }),
      p99: compareMetric('p99', k6.p99_ms, older?.k6.p99_ms, { digits: 3, unit: ' ms' }),
      Errors: compareMetric('Errors', k6.error_rate * 100, older ? older.k6.error_rate * 100 : undefined, { digits: 1, unit: '%' }),
    }),
    tableColumns: ['Run', 'Commit', 'Date', 'Req/s', 'Δ Req/s', 'Errors', 'p99'],
    tableRows: proxyRuns.map((item, index) => {
      const previousRun = proxyRuns[index + 1]
      return [
        String(item.run_number),
        item.short_sha,
        formatDate(item.timestamp),
        formatNumber(item.k6.req_per_s, 0),
        signedPercent(percentChange(item.k6.req_per_s, previousRun?.k6.req_per_s)),
        formatPercent(item.k6.error_rate),
        `${formatNumber(item.k6.p99_ms, 3)} ms`,
      ]
    }),
    tableNote: 'Newest first. Δ compares throughput with the next-older published run.',
  }
}

function proxyStagesModal(): GraphModalState {
  const stages = latestProxy.stages
  return {
    ...blankModal(),
    eyebrow: '01 / Proxy overhead',
    title: 'Proxy stage cost detail',
    description: 'Latest-run stage breakdown at p50, p95, p99, and p999. The measured total is proxy-level, not a naive sum of rows.',
    sourceHref: latestProxy.run_url,
    chartKind: 'bar',
    barLabels: ['Auth LRU', 'Auth gRPC', 'Rate limit', 'Directive', 'Prompt'],
    barSeries: [
      { label: 'p50', values: stageRows.value.map(item => item.value), color: 'var(--chart-lime)', suffix: ' µs', digits: 1 },
    ],
    selectionLabel: `Run ${latestProxy.run_number} · ${formatDate(latestProxy.timestamp)}`,
    summary: [
      { label: 'Measured total', value: micro(stages.total_overhead_p50_ms), note: 'proxy p50' },
      { label: 'Rate limit', value: micro(stages.rate_limit_p50_ms), note: 'largest stage', color: 'var(--chart-pink)' },
      { label: 'Auth cache', value: micro(stages.auth_lru_p50_ms), color: 'var(--chart-lime)' },
      { label: 'Auth gRPC', value: micro(stages.auth_grpc_p50_ms), color: 'var(--chart-blue)' },
    ],
    tableColumns: ['Stage', 'p50', 'p95', 'p99', 'p999'],
    tableRows: [
      ['Auth LRU', micro(stages.auth_lru_p50_ms), micro(stages.auth_lru_p95_ms), micro(stages.auth_lru_p99_ms), micro(stages.auth_lru_p999_ms)],
      ['Auth gRPC', micro(stages.auth_grpc_p50_ms), micro(stages.auth_grpc_p95_ms), micro(stages.auth_grpc_p99_ms), micro(stages.auth_grpc_p999_ms)],
      ['Rate limit', micro(stages.rate_limit_p50_ms), micro(stages.rate_limit_p95_ms), micro(stages.rate_limit_p99_ms), micro(stages.rate_limit_p999_ms)],
      ['Directive resolve', micro(stages.directive_resolve_p50_ms), micro(stages.directive_resolve_p95_ms), micro(stages.directive_resolve_p99_ms), micro(stages.directive_resolve_p999_ms)],
      ['Prompt inject', micro(stages.prompt_inject_p50_ms), micro(stages.prompt_inject_p95_ms), micro(stages.prompt_inject_p99_ms), micro(stages.prompt_inject_p999_ms)],
      ['Measured total', micro(stages.total_overhead_p50_ms), micro(stages.total_overhead_p95_ms), micro(stages.total_overhead_p99_ms), micro(stages.total_overhead_p999_ms)],
    ],
    tableNote: 'Microseconds. Latest published run only.',
  }
}

function hnswModal(kind: 'latency' | 'recall' | 'method'): GraphModalState {
  const latestRow = hnswRows.value[hnswRows.value.length - 1]
  const title = kind === 'recall' ? 'Recall@10 detail' : kind === 'method' ? 'Index and method detail' : 'HNSW search latency detail'
  return {
    ...blankModal(),
    eyebrow: '02 / Memory retrieval',
    title,
    description: 'Published pgvector HNSW cells. The profile stops at 100k rows; the 1M cell is not reported.',
    sourceHref: latestHnsw.run_url,
    chartKind: 'bar',
    barLabels: hnswLabels.value,
    barSeries: kind === 'recall'
      ? [{ label: 'Recall@10', values: hnswRows.value.map(item => item.recall_at_10 * 100), color: 'var(--chart-lime)', suffix: '%', digits: 1 }]
      : hnswSeries.value,
    selectionLabel: `Run ${latestHnsw.run_number} · ${formatDate(latestHnsw.timestamp)}`,
    summary: [
      { label: 'p50 at 100k', value: latestRow ? `${formatNumber(latestRow.latency_ms_p50, 1)} ms` : '—', color: 'var(--chart-lime)' },
      { label: 'p95 at 100k', value: latestRow ? `${formatNumber(latestRow.latency_ms_p95, 1)} ms` : '—', note: 'gate metric', color: 'var(--chart-blue)' },
      { label: 'p99 at 100k', value: latestRow ? `${formatNumber(latestRow.latency_ms_p99, 1)} ms` : '—', color: 'var(--chart-pink)' },
      { label: 'Mean recall', value: formatPercent(latestHnsw.mean_recall_at_10), note: `floor ${formatPercent(latestHnsw.gate_summary.recall_floor)}` },
    ],
    tableColumns: ['Corpus', 'Queries', 'Recall@10', 'p50', 'p95', 'p99', 'p95 CI', 'Build'],
    tableRows: hnswRows.value.map(item => [
      item.corpus_size.toLocaleString(),
      String(item.query_count),
      formatPercent(item.recall_at_10),
      `${formatNumber(item.latency_ms_p50, 1)} ms`,
      `${formatNumber(item.latency_ms_p95, 1)} ms`,
      `${formatNumber(item.latency_ms_p99, 1)} ms`,
      `${formatNumber(item.latency_ms_p95_ci_low, 1)}–${formatNumber(item.latency_ms_p95_ci_high, 1)} ms`,
      item.index_build_mode,
    ]),
    tableNote: `Warmup ${latestHnsw.methodology.warmup_queries} queries per cell. ef_search=${latestHnsw.methodology.ef_search}; embeddings ${latestHnsw.methodology.dim}-dim with ${latestHnsw.methodology.active_dims} active.`,
  }
}

function rankingModal(row: number): GraphModalState {
  const run = rankingRuns[row] ?? latestRanking
  const older = rankingRuns[row + 1]
  const metrics = run.metrics
  return {
    ...blankModal(),
    eyebrow: '03 / Ranking quality',
    title: 'Ranking quality history',
    description: 'Gold-set metrics across published runs. A ceiling result is a regression guard, not evidence of broad ranking quality. Hover to preview a run; click to pin it.',
    sourceHref: run.run_url,
    chartKind: 'bar',
    barLabels: ['P@5', 'R@10', 'MRR', 'Order', 'Category'],
    barYTicks: 5,
    barSeries: [
      { label: 'Score', values: [metrics.precision_at_5, metrics.recall_at_10, metrics.mrr, metrics.expected_order_match, metrics.top_category_accuracy].map(value => value * 100), color: 'var(--chart-lime)', suffix: '%', digits: 1 },
    ],
    selectable: true,
    selectionLabel: `Run ${run.run_number} · ${formatDate(run.timestamp)}`,
    summary: summaryWith([
      { label: 'P@5', value: formatPercent(metrics.precision_at_5), note: 'precision', color: 'var(--chart-lime)' },
      { label: 'R@10', value: formatPercent(metrics.recall_at_10), note: 'recall', color: 'var(--chart-blue)' },
      { label: 'MRR', value: formatPercent(metrics.mrr), note: 'rank', color: 'var(--chart-pink)' },
      { label: 'Order', value: formatPercent(metrics.expected_order_match), note: 'sequence', color: 'var(--chart-violet)' },
    ], {
      'P@5': compareMetric('P@5', metrics.precision_at_5 * 100, older ? older.metrics.precision_at_5 * 100 : undefined, { digits: 1, unit: '%', higherIsBetter: true }),
      'R@10': compareMetric('R@10', metrics.recall_at_10 * 100, older ? older.metrics.recall_at_10 * 100 : undefined, { digits: 1, unit: '%', higherIsBetter: true }),
      MRR: compareMetric('MRR', metrics.mrr * 100, older ? older.metrics.mrr * 100 : undefined, { digits: 1, unit: '%', higherIsBetter: true }),
      Order: compareMetric('Order', metrics.expected_order_match * 100, older ? older.metrics.expected_order_match * 100 : undefined, { digits: 1, unit: '%', higherIsBetter: true }),
    }),
    tableColumns: ['Run', 'Commit', 'Date', 'P@5', 'R@10', 'MRR', 'Order', 'Category', 'Status'],
    tableRows: rankingRuns.map(item => [
      String(item.run_number),
      item.short_sha,
      formatDate(item.timestamp),
      formatPercent(item.metrics.precision_at_5),
      formatPercent(item.metrics.recall_at_10),
      formatPercent(item.metrics.mrr),
      formatPercent(item.metrics.expected_order_match),
      formatPercent(item.metrics.top_category_accuracy),
      item.status,
    ]),
    tableNote: 'Newest first. Gold set v1; every published metric is at the ceiling.',
  }
}

function writeModal(kind: 'history' | 'latest' | 'gate', row: number): GraphModalState {
  const run = writeRuns[row] ?? latestWrite
  const older = writeRuns[row + 1]
  const metrics = run.metrics
  const title = kind === 'latest' ? 'Write latency detail' : kind === 'gate' ? 'Write gate detail' : 'Write latency history'
  return {
    ...blankModal(),
    eyebrow: '04 / Write pipeline',
    title,
    description: 'End-to-end memory write latency. The p95 gate is 200 ms; the tail is reported rather than hidden. Hover to preview a run; click to pin it.',
    sourceHref: run.run_url,
    chartKind: kind === 'history' ? 'line' : 'meter',
    lineSeries: [
      { label: 'p50', values: writeHistory.value.map(item => item.metrics.latency_ms_p50), color: 'var(--chart-lime)', suffix: ' ms', digits: 1 },
      { label: 'p95', values: writeHistory.value.map(item => item.metrics.latency_ms_p95), color: 'var(--chart-blue)', suffix: ' ms', digits: 1 },
      { label: 'p99', values: writeHistory.value.map(item => item.metrics.latency_ms_p99), color: 'var(--chart-pink)', suffix: ' ms', digits: 1 },
    ],
    lineLabels: writeModalLabels.value,
    threshold: 200,
    thresholdLabel: '200 ms gate',
    meterItems: writePercentilesFor(run),
    meterThreshold: { value: 200, label: 'p95 gate · 200 ms' },
    selectable: true,
    activeIndex: kind === 'history' ? writeRuns.length - 1 - row : null,
    selectionLabel: `Run ${run.run_number} · ${formatDate(run.timestamp)}`,
    summary: summaryWith([
      { label: 'p50', value: `${formatNumber(metrics.latency_ms_p50, 1)} ms`, note: 'median', color: 'var(--chart-lime)' },
      { label: 'p95', value: `${formatNumber(metrics.latency_ms_p95, 1)} ms`, note: 'gate 200 ms', color: 'var(--chart-blue)' },
      { label: 'p99', value: `${formatNumber(metrics.latency_ms_p99, 1)} ms`, note: `${formatNumber(metrics.latency_ms_p99 / metrics.latency_ms_p95, 1)}× p95`, color: 'var(--chart-pink)' },
      { label: 'p99/p95', value: `${formatNumber(metrics.latency_ms_p99 / metrics.latency_ms_p95, 1)}×`, note: 'tail spread', color: 'var(--chart-violet)' },
    ], {
      p50: compareMetric('p50', metrics.latency_ms_p50, older?.metrics.latency_ms_p50, { digits: 1, unit: ' ms' }),
      p95: compareMetric('p95', metrics.latency_ms_p95, older?.metrics.latency_ms_p95, { digits: 1, unit: ' ms' }),
      p99: compareMetric('p99', metrics.latency_ms_p99, older?.metrics.latency_ms_p99, { digits: 1, unit: ' ms' }),
      'p99/p95': compareMetric('p99/p95', metrics.latency_ms_p99 / metrics.latency_ms_p95, older ? older.metrics.latency_ms_p99 / older.metrics.latency_ms_p95 : undefined, { digits: 1, unit: '×' }),
    }),
    tableColumns: ['Run', 'Commit', 'Date', 'p50', 'p95', 'p99', 'Δ p95', 'Status'],
    tableRows: writeRuns.map((item, index) => {
      const previousRun = writeRuns[index + 1]
      return [
        String(item.run_number),
        item.short_sha,
        formatDate(item.timestamp),
        `${formatNumber(item.metrics.latency_ms_p50, 1)} ms`,
        `${formatNumber(item.metrics.latency_ms_p95, 1)} ms`,
        `${formatNumber(item.metrics.latency_ms_p99, 1)} ms`,
        signedPercent(percentChange(item.metrics.latency_ms_p95, previousRun?.metrics.latency_ms_p95)),
        item.status,
      ]
    }),
    tableNote: 'Newest first. Δ compares p95 with the next-older published run.',
  }
}

function extractionModal(kind: 'categories' | 'summary', row: number): GraphModalState {
  const run = extractionRuns[row] ?? latestExtraction
  const older = extractionRuns[row + 1]
  const categories = extractionCategories.map(category => ({
    name: category.charAt(0).toUpperCase() + category.slice(1),
    precision: run.metrics[`precision_${category}`],
    recall: run.metrics[`recall_${category}`],
  }))
  const macro = [
    { label: 'Macro precision', value: run.metrics.precision_macro, previous: older?.metrics.precision_macro },
    { label: 'Macro recall', value: run.metrics.recall_macro, previous: older?.metrics.recall_macro },
    { label: 'Category accuracy', value: run.metrics.category_assignment_accuracy, previous: older?.metrics.category_assignment_accuracy },
    { label: 'Temporal accuracy', value: run.metrics.temporal_field_accuracy, previous: older?.metrics.temporal_field_accuracy },
  ]
  return {
    ...blankModal(),
    eyebrow: '05 / Extraction quality',
    title: kind === 'summary' ? 'Extraction run summary' : 'Precision and recall by category',
    description: `Cassette-mode extraction against the v1 gold set. ${extractionGate.value.total} gate checks; the regression limit is three percentage points. Hover to preview a run; click to pin it.`,
    sourceHref: run.run_url,
    chartKind: 'bar',
    barLabels: kind === 'summary' ? ['Precision', 'Recall', 'Category', 'Temporal'] : categories.map(category => category.name),
    barYTicks: 5,
    barSeries: kind === 'summary'
      ? [{ label: 'Score', values: macro.map(item => item.value * 100), color: 'var(--chart-lime)', suffix: '%', digits: 1 }]
      : [
          { label: 'Precision', values: categories.map(category => category.precision * 100), color: 'var(--chart-lime)', suffix: '%', digits: 1 },
          { label: 'Recall', values: categories.map(category => category.recall * 100), color: 'var(--chart-blue)', suffix: '%', digits: 1 },
        ],
    selectable: true,
    selectionLabel: `Run ${run.run_number} · ${formatDate(run.timestamp)}`,
    summary: summaryWith([
      { label: 'Macro precision', value: formatPercent(run.metrics.precision_macro), note: 'precision', color: 'var(--chart-lime)' },
      { label: 'Macro recall', value: formatPercent(run.metrics.recall_macro), note: 'recall', color: 'var(--chart-blue)' },
      { label: 'Category', value: formatPercent(run.metrics.category_assignment_accuracy), note: 'assignment', color: 'var(--chart-pink)' },
      { label: 'Temporal', value: formatPercent(run.metrics.temporal_field_accuracy), note: 'fields', color: 'var(--chart-violet)' },
    ], {
      'Macro precision': compareMetric('Macro precision', run.metrics.precision_macro * 100, older ? older.metrics.precision_macro * 100 : undefined, { digits: 1, unit: '%', higherIsBetter: true }),
      'Macro recall': compareMetric('Macro recall', run.metrics.recall_macro * 100, older ? older.metrics.recall_macro * 100 : undefined, { digits: 1, unit: '%', higherIsBetter: true }),
      Category: compareMetric('Category', run.metrics.category_assignment_accuracy * 100, older ? older.metrics.category_assignment_accuracy * 100 : undefined, { digits: 1, unit: '%', higherIsBetter: true }),
      Temporal: compareMetric('Temporal', run.metrics.temporal_field_accuracy * 100, older ? older.metrics.temporal_field_accuracy * 100 : undefined, { digits: 1, unit: '%', higherIsBetter: true }),
    }),
    tableColumns: ['Run', 'Commit', 'Date', 'Precision', 'Recall', 'Category', 'Temporal', 'Checks', 'Status'],
    tableRows: extractionRuns.map(item => [
      String(item.run_number),
      item.short_sha,
      formatDate(item.timestamp),
      formatPercent(item.metrics.precision_macro),
      formatPercent(item.metrics.recall_macro),
      formatPercent(item.metrics.category_assignment_accuracy),
      formatPercent(item.metrics.temporal_field_accuracy),
      `${item.gate_summary.checks.filter(check => check.ok).length} / ${item.gate_summary.checks.length}`,
      item.status,
    ]),
    tableNote: 'Newest first. Perfect scores reflect a saturated fixed cassette.',
  }
}

function goBenchmarksModal(): GraphModalState {
  const rows = goBenchmarks.value
  const sorted = [...rows].sort((a, b) => b.ns - a.ns)
  const slowest = sorted[0]
  const fastest = sorted[sorted.length - 1]
  const samples = rows[0]?.samples ?? 0
  return {
    ...blankModal(),
    eyebrow: '01 / Proxy overhead',
    title: 'Go microbenchmarks',
    description: 'One row per Go benchmark, sorted slowest first. Bars use a log time axis; the whisker marks the 95% confidence interval. The PR-time gate compares these means, not k6 p99.',
    sourceHref: latestProxy.run_url,
    chartKind: 'list',
    listItems: goBenchItems.value,
    selectionLabel: `Run ${latestProxy.run_number} · ${formatDate(latestProxy.timestamp)}`,
    summary: [
      { label: 'Benchmarks', value: String(rows.length), note: `${samples} samples each` },
      { label: 'Slowest', value: slowest ? `${formatNumber(slowest.ns, 0)} ns` : '—', note: slowest?.label },
      { label: 'Fastest', value: fastest ? `${formatNumber(fastest.ns, 1)} ns` : '—', note: fastest?.label },
      { label: 'Peak allocs', value: formatNumber(Math.max(...rows.map(row => row.allocs)), 0), note: 'allocs per op' },
    ],
    tableColumns: ['Benchmark', 'Path', 'ns/op', '95% CI', 'allocs/op', 'bytes/op'],
    tableRows: rows.map(row => [
      row.label,
      row.family,
      formatNumber(row.ns, 1),
      `${formatNumber(row.ciLow, 0)}–${formatNumber(row.ciHigh, 0)} ns`,
      formatNumber(row.allocs, 0),
      formatNumber(row.bytes, 0),
    ]),
    tableNote: 'Go benchmark means from the same published run. Bars and CI share a log time axis.',
  }
}

function openProxyLatency() {
  openGraph('proxy-latency')
}

function openProxyThroughput() {
  openGraph('proxy-throughput')
}

function openProxyStages() {
  openGraph('proxy-stages')
}

function openGoBenchmarks() {
  openGraph('go-benchmarks')
}

function openHnsw(kind: 'latency' | 'recall' | 'method') {
  openGraph(kind === 'latency' ? 'hnsw-latency' : kind === 'recall' ? 'hnsw-recall' : 'hnsw-method')
}

function openRanking() {
  openGraph('ranking')
}

function openWrite(kind: 'history' | 'latest' | 'gate') {
  openGraph(kind === 'history' ? 'write-history' : kind === 'latest' ? 'write-latest' : 'write-gate')
}

function openExtraction(kind: 'categories' | 'summary') {
  openGraph(kind === 'categories' ? 'extraction-categories' : 'extraction-summary')
}

watch(activeSection, async (id) => {
  await nextTick()
  const nav = mobileNav.value
  const link = nav?.querySelector<HTMLElement>(`a[href="#${id}"]`)
  if (!nav || !link) return

  const navRect = nav.getBoundingClientRect()
  const linkRect = link.getBoundingClientRect()
  const target = nav.scrollLeft + linkRect.left - navRect.left - (nav.clientWidth - linkRect.width) / 2
  nav.scrollTo({ left: Math.max(0, target), behavior: 'smooth' })
})

function updateActiveSection() {
  const threshold = 160
  let current = 'proxy'
  for (const id of sectionIds) {
    const element = document.getElementById(id)
    if (element && element.getBoundingClientRect().top <= threshold) current = id
  }
  activeSection.value = current
}

onMounted(() => {
  updateViewport()
  updateActiveSection()
  window.addEventListener('scroll', updateActiveSection, { passive: true })
  window.addEventListener('resize', updateActiveSection)
  window.addEventListener('resize', updateViewport)
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', updateActiveSection)
  window.removeEventListener('resize', updateActiveSection)
  window.removeEventListener('resize', updateViewport)
})

function micro(ms: number) {
  const value = ms * 1000
  const digits = value < 1 ? 3 : value < 10 ? 2 : 1
  return `${formatNumber(value, digits)} µs`
}

function compactNs(value: number) {
  if (value >= 1_000_000) return `${formatNumber(value / 1_000_000, 2)} ms`
  if (value >= 1_000) return `${formatNumber(value / 1_000, 1)} µs`
  return `${formatNumber(value, 0)} ns`
}
</script>

<template>
  <div class="site-shell py-12 lg:py-16">
    <section class="border-b border-[var(--site-line)] pb-10">
      <p class="m-0 font-mono text-[0.6rem] uppercase tracking-[0.14em] text-[var(--site-muted)]">
        Benchmarks
      </p>
      <h1 class="site-display mt-6 max-w-4xl text-5xl sm:text-6xl lg:text-7xl">
        Every number carries its workload.
      </h1>
    </section>

    <div class="mt-16 grid gap-10 xl:grid-cols-[14.5rem_minmax(0,1fr)] xl:gap-12">
      <aside class="hidden xl:block">
        <div class="sticky top-24">
          <BenchmarkNav :suites="navSuites" :active="activeSection" />
        </div>
      </aside>

      <div class="min-w-0">
        <div class="sticky top-[65px] z-20 -mx-4 mb-8 border-y border-[var(--site-line)] bg-[color-mix(in_srgb,var(--site-bg)_92%,transparent)] px-4 py-2 backdrop-blur-xl xl:hidden">
          <div ref="mobileNav" class="site-scrollbar flex gap-1 overflow-x-auto">
            <a
              v-for="item in mobileNavItems"
              :key="item.href"
              :href="item.href"
              class="flex shrink-0 items-center gap-1.5 rounded-full px-3 py-2 font-mono text-[0.56rem] uppercase tracking-[0.08em] transition-colors"
              :class="activeSection === item.href.slice(1)
                ? 'bg-[color-mix(in_srgb,var(--site-signal)_12%,transparent)] text-[var(--site-signal)]'
                : 'text-[var(--site-muted)]'"
            >
              <UIcon :name="item.icon" class="size-3.5" />
              {{ item.shortTitle }}
            </a>
          </div>
        </div>

        <section id="proxy" class="scroll-mt-28">
          <BenchmarkSectionHeader
            index="01"
            label="Proxy overhead"
            title="The warm path, without the provider."
            description="A local k6 run against the Go proxy with auth, rate limiting, directive resolution, and prompt injection active. Provider time is excluded."
            icon="i-lucide-gauge"
            :tag="suites[0]?.tag"
            :run-url="latestProxy.run_url"
            :run-number="latestProxy.run_number"
          />

          <div class="mt-9 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <BenchmarkGraphCard
              title="Latency over runs"
              :meta="`last ${proxyWindow.length} of ${proxyHistory.length} runs`"
              :legend="proxyPercentileLegend"
              caption="Oldest at left. Local k6 percentiles, not a hosted service-level objective."
              @expand="openProxyLatency"
            >
              <BenchmarkChart :series="proxyPercentileSeries" :labels="proxyLabels" :width="360" :height="170" minimal :filled="false" />
            </BenchmarkGraphCard>

            <BenchmarkGraphCard
              title="Throughput"
              :meta="`${latestProxy.k6.duration_s}s · ${latestProxy.k6.vus} VUs`"
              :legend="proxyThroughputLegend"
              :caption="`Peak ${formatNumber(Math.max(...proxyThroughput), 0)} req/s · ${formatPercent(latestProxy.k6.error_rate)} errors. Provider time excluded.`"
              @expand="openProxyThroughput"
            >
              <BenchmarkChart :series="proxyThroughputSeries" :labels="proxyThroughputLabels" :width="360" :height="170" minimal :filled="false" />
            </BenchmarkGraphCard>

            <BenchmarkGraphCard
              title="Stage cost at p50"
              meta="microseconds · measured total"
              caption="Rate limiting dominates. Total is the proxy-level p50, not a naive sum."
              @expand="openProxyStages"
            >
              <BenchmarkMeter :items="stageRows" :total="stageTotal" />
            </BenchmarkGraphCard>
          </div>

          <div class="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[0.55rem] uppercase tracking-[0.08em] text-[var(--site-muted)]">
            <span>p95 {{ formatNumber(latestProxy.k6.p95_ms, 3) }} ms</span>
            <span class="size-1 rounded-full bg-[var(--site-muted)]" />
            <span>p999 {{ formatNumber(latestProxy.k6.p999_ms, 3) }} ms</span>
            <span class="size-1 rounded-full bg-[var(--site-muted)]" />
            <span>Baseline {{ latestProxy.baseline_sha.slice(0, 7) }}</span>
            <span class="size-1 rounded-full bg-[var(--site-muted)]" />
            <span>Go {{ latestProxy.go_version }} / k6 {{ latestProxy.k6_version }}</span>
          </div>

          <div class="mt-3">
            <BenchmarkGraphCard
              title="Go microbenchmarks"
              :meta="`${goBenchmarks.length} benchmarks · ns/op · log scale · ${latestProxy.go_version}`"
              :legend="goLegend"
              caption="Go benchmark means from the same published run. Bars end at the mean; the whisker marks the 95% confidence interval. The PR gate compares these means, not k6 p99."
              @expand="openGoBenchmarks"
            >
              <BenchmarkMicrobenchChart :items="goBenchItems" :compact="isCompact" />
            </BenchmarkGraphCard>
          </div>
        </section>

        <section id="retrieval" class="mt-24 scroll-mt-28 border-t border-[var(--site-line)] pt-14">
          <BenchmarkSectionHeader
            index="02"
            label="Memory retrieval"
            title="Recall holds as the corpus grows."
            description="pgvector HNSW search with a planted near-neighbour check. The published profile stops at 100k rows; the 1M cell is not reported."
            icon="i-lucide-database"
            :tag="suites[1]?.tag"
            :run-url="latestHnsw.run_url"
            :run-number="latestHnsw.run_number"
          />

          <div class="mt-9 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <BenchmarkGraphCard
              title="Search latency by corpus"
              :meta="`${hnswRows.length} corpus sizes · ${latestHnsw.methodology.warmup_queries} warmup / cell`"
              :legend="hnswLegend"
              caption="Grouped bars. Warmup excluded. p95 confidence intervals are listed below."
              @expand="openHnsw('latency')"
            >
              <BenchmarkBarChart :labels="hnswLabels" :series="hnswSeries" :width="360" :height="184" :show-legend="false" :show-values="true" />
            </BenchmarkGraphCard>

            <BenchmarkGraphCard
              title="Recall@10"
              meta="planted near-neighbour"
              :caption="`Floor ${formatPercent(latestHnsw.gate_summary.recall_floor)}. The 1M cell is absent on this profile.`"
              @expand="openHnsw('recall')"
            >
              <div class="w-full">
                <p class="m-0 text-5xl font-semibold tracking-[-0.065em]">{{ formatPercent(latestHnsw.mean_recall_at_10) }}</p>
                <p class="m-0 mt-1 text-xs text-[var(--site-muted)]">mean recall across published cells</p>
                <div class="mt-6 space-y-4">
                  <div v-for="row in hnswRecallRows" :key="row.label">
                    <div class="flex items-center justify-between gap-3 text-[0.7rem]">
                      <span class="text-[var(--site-muted)]">{{ row.label }}</span>
                      <span class="font-mono tabular-nums">{{ row.display }}</span>
                    </div>
                    <div class="mt-1.5 h-2 overflow-hidden rounded-full bg-[var(--site-code-bg)]">
                      <div class="h-full rounded-full bg-[var(--chart-lime)]" :style="{ width: `${row.value * 100}%` }" />
                    </div>
                  </div>
                </div>
              </div>
            </BenchmarkGraphCard>

            <BenchmarkGraphCard
              title="Gate and method"
              meta="recall gate · pass"
              caption="Recall checks for a planted near-neighbour in the top 10. It is not a general semantic-quality score."
              @expand="openHnsw('method')"
            >
              <dl class="m-0 w-full self-start divide-y divide-[var(--site-line)] text-[0.72rem] leading-relaxed">
                <div class="flex items-baseline justify-between gap-4 py-2.5 first:pt-0">
                  <dt class="shrink-0 text-[var(--site-muted)]">Index</dt>
                  <dd class="m-0 text-right">HNSW · m=16 · ef_construction=64</dd>
                </div>
                <div class="flex items-baseline justify-between gap-4 py-2.5">
                  <dt class="shrink-0 text-[var(--site-muted)]">Search</dt>
                  <dd class="m-0 text-right">ef_search=64 · min similarity 0.70</dd>
                </div>
                <div class="flex items-baseline justify-between gap-4 py-2.5">
                  <dt class="shrink-0 text-[var(--site-muted)]">Embedding</dt>
                  <dd class="m-0 text-right">{{ latestHnsw.methodology.dim }}-dim · {{ latestHnsw.methodology.active_dims }} active</dd>
                </div>
                <div class="flex items-baseline justify-between gap-4 py-2.5 last:pb-0">
                  <dt class="shrink-0 text-[var(--site-muted)]">Iterative scan</dt>
                  <dd class="m-0 text-right">off</dd>
                </div>
              </dl>
            </BenchmarkGraphCard>
          </div>

          <div class="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[0.55rem] uppercase tracking-[0.08em] text-[var(--site-muted)]">
            <span v-for="row in hnswCi" :key="row.label">p95 CI {{ row.label }} {{ row.value }}</span>
            <span class="size-1 rounded-full bg-[var(--site-muted)]" />
            <span>1M cell absent</span>
          </div>
        </section>

        <section id="ranking" class="mt-24 scroll-mt-28 border-t border-[var(--site-line)] pt-14">
          <BenchmarkSectionHeader
            index="03"
            label="Ranking quality"
            title="The gold set is at its ceiling."
            :description="`Twenty queries over fifty-one memories. ${rankingAtCeiling === rankingRows.length ? 'Every published ranking metric is 1.0, which means this set is saturated, not that ranking generalizes everywhere.' : 'The latest run is not at the ceiling; see the gate checks before citing ranking quality.'}`"
            icon="i-lucide-list-checks"
            :tag="suites[2]?.tag"
            :run-url="latestRanking.run_url"
            :run-number="latestRanking.run_number"
          />

          <div class="mt-9 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <BenchmarkGraphCard
              title="Gold-set score"
              :meta="`${latestRanking.query_count} queries / ${latestRanking.memory_count} memories`"
              caption="A ceiling result is a regression guard, not evidence of broad ranking quality."
              @expand="openRanking"
            >
              <div class="grid w-full place-items-center py-2">
                <div
                  class="grid size-40 place-items-center rounded-full shadow-[0_0_50px_-22px_var(--chart-lime)]"
                  :style="{ background: 'repeating-conic-gradient(var(--chart-lime) 0deg 69deg, transparent 69deg 72deg)' }"
                >
                  <div class="grid size-32 place-items-center rounded-full bg-[var(--site-bg)] text-center">
                    <div>
                      <p class="m-0 text-4xl font-semibold tracking-[-0.06em]">{{ rankingAtCeiling }} / {{ rankingRows.length }}</p>
                      <p class="m-0 mt-1 font-mono text-[0.5rem] uppercase tracking-[0.1em] text-[var(--site-muted)]">at 1.0</p>
                    </div>
                  </div>
                </div>
              </div>
            </BenchmarkGraphCard>

            <BenchmarkGraphCard
              title="Metric ladder"
              :meta="`gate v1 · ${rankingGate.passed} / ${rankingGate.total} checks`"
              :caption="rankingAtCeiling === rankingRows.length ? 'Every published ranking metric is at the ceiling for this set.' : 'The latest run is below the ceiling for at least one metric.'"
              @expand="openRanking"
            >
              <BenchmarkMeter :items="rankingRows.map(row => ({ label: row.label, value: row.value * 100, display: formatPercent(row.value), color: 'var(--chart-lime)' }))" />
            </BenchmarkGraphCard>

            <BenchmarkGraphCard
              title="Run context"
              meta="saturated set"
              caption="Twenty queries and fifty-one memories. The set is intentionally small."
              @expand="openRanking"
            >
              <dl class="m-0 w-full self-start divide-y divide-[var(--site-line)] text-[0.74rem]">
                <div class="flex items-center justify-between gap-4 py-3 first:pt-0">
                  <dt class="text-[var(--site-muted)]">Gold set</dt>
                  <dd class="m-0 font-mono">{{ latestRanking.gold_set }}</dd>
                </div>
                <div class="flex items-center justify-between gap-4 py-3">
                  <dt class="text-[var(--site-muted)]">Queries</dt>
                  <dd class="m-0 font-mono">{{ latestRanking.query_count }}</dd>
                </div>
                <div class="flex items-center justify-between gap-4 py-3">
                  <dt class="text-[var(--site-muted)]">Memories</dt>
                  <dd class="m-0 font-mono">{{ latestRanking.memory_count }}</dd>
                </div>
                <div class="flex items-center justify-between gap-4 py-3 last:pb-0">
                  <dt class="text-[var(--site-muted)]">Published</dt>
                  <dd class="m-0 font-mono">{{ formatDate(latestRanking.timestamp) }}</dd>
                </div>
              </dl>
            </BenchmarkGraphCard>
          </div>
        </section>

        <section id="writes" class="mt-24 scroll-mt-28 border-t border-[var(--site-line)] pt-14">
          <BenchmarkSectionHeader
            index="04"
            label="Write pipeline"
            title="Fast median, visible tail."
            description="Forty end-to-end writes through memory persistence. The p95 gate is 200 ms; the tail is reported rather than hidden."
            icon="i-lucide-arrow-down-to-line"
            :tag="suites[3]?.tag"
            :run-url="latestWrite.run_url"
            :run-number="latestWrite.run_number"
          />

          <div class="mt-9 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <BenchmarkGraphCard
              title="Latency over runs"
              :meta="`${writeHistory.length} runs · amber = 200 ms gate`"
              :legend="writeLegend"
              caption="Oldest at left. The tail is plotted rather than hidden."
              @expand="openWrite('history')"
            >
              <BenchmarkChart :series="writeSeries" :labels="writeLabels" :width="360" :height="170" minimal :filled="false" :threshold="200" threshold-label="200 ms gate" />
            </BenchmarkGraphCard>

            <BenchmarkGraphCard
              title="Latest latency"
              :meta="`${latestWrite.iterations} iterations`"
              :caption="`The p99 is ${formatNumber(latestWrite.metrics.latency_ms_p99 / latestWrite.metrics.latency_ms_p95, 1)}× the p95. That spread is why the gate is not the whole story.`"
              @expand="openWrite('latest')"
            >
              <BenchmarkMeter :items="writePercentiles" :threshold="{ value: 200, label: 'p95 gate · 200 ms' }" />
            </BenchmarkGraphCard>

            <BenchmarkGraphCard
              title="Gate"
              meta="p95 limit · 200 ms"
              caption="The regression limit is +20% against the baseline."
              @expand="openWrite('gate')"
            >
              <div class="w-full self-start">
                <p class="m-0 text-5xl font-semibold tracking-[-0.065em]">{{ formatNumber(latestWrite.metrics.latency_ms_p95, 1) }} <span class="text-base font-normal tracking-normal text-[var(--site-muted)]">ms</span></p>
                <p class="m-0 mt-1 text-xs text-[var(--site-muted)]">p95 / 200 ms</p>
                <dl class="m-0 mt-6 divide-y divide-[var(--site-line)] text-[0.74rem]">
                  <div class="flex items-center justify-between gap-4 py-3 first:pt-0">
                    <dt class="text-[var(--site-muted)]">p95 vs baseline</dt>
                    <dd class="m-0 font-mono">{{ formatPercent(writeRegression === null ? null : writeRegression / 100) }}</dd>
                  </div>
                  <div class="flex items-center justify-between gap-4 py-3">
                    <dt class="text-[var(--site-muted)]">Limit</dt>
                    <dd class="m-0 font-mono">+20%</dd>
                  </div>
                  <div class="flex items-center justify-between gap-4 py-3 last:pb-0">
                    <dt class="text-[var(--site-muted)]">p99 / p95</dt>
                    <dd class="m-0 font-mono">{{ formatNumber(latestWrite.metrics.latency_ms_p99 / latestWrite.metrics.latency_ms_p95, 1) }}×</dd>
                  </div>
                </dl>
              </div>
            </BenchmarkGraphCard>
          </div>
        </section>

        <section id="extraction" class="mt-24 scroll-mt-28 border-t border-[var(--site-line)] pt-14">
          <BenchmarkSectionHeader
            index="05"
            label="Extraction quality"
            title="Precision and recall by category."
            :description="`Cassette-mode extraction against the v1 gold set: ${latestExtraction.conversation_count} conversations, ${extractionGate.total} gate checks, and a 3 percentage-point regression limit.`"
            icon="i-lucide-scan-text"
            :tag="suites[4]?.tag"
            :run-url="latestExtraction.run_url"
            :run-number="latestExtraction.run_number"
          />

          <div class="mt-9 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <BenchmarkGraphCard
              title="Category quality"
              meta="precision / recall"
              :legend="extractionLegend"
              caption="A fixed cassette and a small gold set. This is a regression signal, not live model quality."
              class="md:col-span-2"
              @expand="openExtraction('categories')"
            >
              <div class="w-full">
                <div
                  v-for="row in extractionRows"
                  :key="row.name"
                  class="grid gap-3 border-b border-[var(--site-line)] py-3.5 first:pt-0 last:border-b-0 last:pb-0 sm:grid-cols-[6rem_1fr] sm:items-center"
                >
                  <span class="text-[0.78rem] font-medium">{{ row.name }}</span>
                  <div class="grid grid-cols-2 gap-5">
                    <div>
                      <div class="flex items-center justify-between gap-2">
                        <span class="flex items-center gap-1.5 font-mono text-[0.5rem] uppercase tracking-[0.08em] text-[var(--site-muted)]"><span class="size-1 rounded-full bg-[var(--chart-lime)]" />Precision</span>
                        <span class="font-mono text-[0.62rem]">{{ formatPercent(row.precision) }}</span>
                      </div>
                      <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[var(--site-code-bg)]">
                        <div class="h-full rounded-full bg-[var(--chart-lime)]" :style="{ width: `${row.precision * 100}%` }" />
                      </div>
                    </div>
                    <div>
                      <div class="flex items-center justify-between gap-2">
                        <span class="flex items-center gap-1.5 font-mono text-[0.5rem] uppercase tracking-[0.08em] text-[var(--site-muted)]"><span class="size-1 rounded-full bg-[var(--chart-blue)]" />Recall</span>
                        <span class="font-mono text-[0.62rem]">{{ formatPercent(row.recall) }}</span>
                      </div>
                      <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[var(--site-code-bg)]">
                        <div class="h-full rounded-full bg-[var(--chart-blue)]" :style="{ width: `${row.recall * 100}%` }" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </BenchmarkGraphCard>

            <BenchmarkGraphCard
              title="Run summary"
              :meta="`${extractionGate.passed} / ${extractionGate.total} gate checks`"
              :caption="extractionGate.passed === extractionGate.total
                ? 'Perfect scores reflect a saturated gold set.'
                : 'The latest run failed gate checks; see the modal for per-check detail.'"
              class="md:col-span-2 xl:col-span-1"
              @expand="openExtraction('summary')"
            >
              <div class="w-full">
                <p class="m-0 text-5xl font-semibold tracking-[-0.065em]">{{ extractionGate.passed }} / {{ extractionGate.total }}</p>
                <p class="m-0 mt-1 text-xs text-[var(--site-muted)]">gate checks pass</p>
                <div class="mt-6 grid grid-cols-2 gap-x-5 gap-y-5">
                  <div v-for="metric in extractionMacro" :key="metric.label">
                    <p class="m-0 text-xl font-medium tracking-[-0.035em]">{{ formatPercent(metric.value) }}</p>
                    <p class="m-0 mt-1 font-mono text-[0.48rem] uppercase tracking-[0.08em] text-[var(--site-muted)]">{{ metric.label }}</p>
                  </div>
                </div>
                <div class="mt-6 space-y-1.5 border-t border-[var(--site-line)] pt-4 font-mono text-[0.54rem] uppercase tracking-[0.08em] text-[var(--site-muted)]">
                  <p class="m-0">{{ latestExtraction.conversation_count }} conversations</p>
                  <p class="m-0">{{ latestExtraction.model }} · {{ latestExtraction.mode }} mode</p>
                  <p class="m-0">gold set {{ latestExtraction.gold_set }} · {{ formatDate(latestExtraction.timestamp) }}</p>
                </div>
              </div>
            </BenchmarkGraphCard>
          </div>
        </section>

        <section id="method" class="mt-24 scroll-mt-28 border-t border-[var(--site-line)] pt-14">
          <BenchmarkSectionHeader
            index="06"
            label="Method / read this before citing"
            title="The boundary is part of the result."
            description="What ran, where it ran, what was excluded, and which claims the evidence can actually support."
            icon="i-lucide-book-open"
          />

          <div class="mt-9 grid gap-10 lg:grid-cols-3">
            <div class="border-t border-[var(--site-line)] pt-5">
              <div class="flex items-center gap-2 text-[var(--site-signal)]">
                <UIcon name="i-lucide-server" class="size-4" />
                <p class="m-0 font-mono text-[0.55rem] uppercase tracking-[0.1em]">01 / Machine</p>
              </div>
              <div class="mt-4 space-y-2 text-sm">
                <p class="m-0">{{ latestProxy.runner_os }} · {{ latestProxy.runner_cpu }}</p>
                <p class="m-0">{{ latestProxy.runner_vcpus }} vCPU · {{ latestProxy.runner_ram_gb }} GB RAM</p>
                <p class="m-0">Go {{ latestProxy.go_version }} · k6 {{ latestProxy.k6_version }}</p>
                <p class="m-0">{{ latestProxy.profile }} profile · {{ latestProxy.k6.vus }} VUs · {{ latestProxy.k6.duration_s }}s</p>
              </div>
            </div>
            <div class="border-t border-[var(--site-line)] pt-5 lg:border-l lg:pl-8">
              <div class="flex items-center gap-2 text-[var(--site-signal)]">
                <UIcon name="i-lucide-shield-check" class="size-4" />
                <p class="m-0 font-mono text-[0.55rem] uppercase tracking-[0.1em]">02 / Boundary</p>
              </div>
              <div class="mt-4 space-y-2 text-sm text-[var(--site-muted)]">
                <p class="m-0"><span class="text-[var(--site-ink)]">Local and CI only.</span> No hosted, HA, multi-region, or restore claim.</p>
                <p class="m-0"><span class="text-[var(--site-ink)]">Warm path.</span> Provider latency and network variance are excluded from proxy overhead.</p>
                <p class="m-0"><span class="text-[var(--site-ink)]">No p99 SLO.</span> The 20 ms target is ratified; it is not a measured hosted result.</p>
              </div>
            </div>
            <div class="border-t border-[var(--site-line)] pt-5 lg:border-l lg:pl-8">
              <div class="flex items-center gap-2 text-[var(--site-signal)]">
                <UIcon name="i-lucide-chart-candlestick" class="size-4" />
                <p class="m-0 font-mono text-[0.55rem] uppercase tracking-[0.1em]">03 / Interpretation</p>
              </div>
              <div class="mt-4 space-y-2 text-sm text-[var(--site-muted)]">
                <p class="m-0">Use percentiles with their workload. Do not compare runs with different profiles or hardware.</p>
                <p class="m-0">The PR-time Go gate is mean-based. <NuxtLink to="/docs/architecture/status-and-evidence" class="site-link">GAP-004</NuxtLink> remains open.</p>
                <p class="m-0">Every chart plots published values. No interpolation or synthetic capacity model.</p>
              </div>
            </div>
          </div>
        </section>

        <section id="raw-data" class="mt-24 scroll-mt-28 border-t border-[var(--site-line)] pt-14">
          <BenchmarkSectionHeader
            index="07"
            label="Raw data"
            title="Published data, inspect the source."
            description="Every chart on this page is rendered from these published files. Download the JSON and inspect the runs directly."
            icon="i-lucide-braces"
            :tag="`${totalRuns} runs / 5 files`"
          />

          <div class="mt-8 border-y border-[var(--site-line)]">
            <div
              v-for="file in jsonFiles"
              :key="file.href"
              class="grid gap-4 border-b border-[var(--site-line)] py-4 last:border-b-0 sm:grid-cols-[1fr_auto_auto] sm:items-center sm:gap-6"
            >
              <div class="flex items-start gap-3">
                <UIcon name="i-lucide-file-json" class="mt-0.5 size-4 shrink-0 text-[var(--site-signal)]" />
                <div>
                  <p class="m-0 text-sm font-medium">{{ file.label }}</p>
                  <p class="m-0 mt-1 text-xs text-[var(--site-muted)]">{{ file.meta.description }}</p>
                  <p class="m-0 mt-1 font-mono text-[0.55rem] uppercase tracking-[0.08em] text-[var(--site-muted)]">
                    {{ file.runs }} runs · {{ formatDate(file.updated) }}
                  </p>
                </div>
              </div>
              <a
                :href="file.href"
                :download="file.href.split('/').at(-1)"
                class="site-button site-button-ghost justify-center whitespace-nowrap"
                :aria-label="`Download ${file.label} JSON`"
              >
                <UIcon name="i-lucide-download" class="size-3.5" />
                Download
              </a>
              <a
                :href="file.href"
                target="_blank"
                rel="noreferrer"
                class="site-mono inline-flex items-center justify-center gap-1 whitespace-nowrap text-[0.58rem] uppercase tracking-[0.1em] text-[var(--site-muted)] transition-colors hover:text-[var(--site-ink)]"
                :aria-label="`Open ${file.label} JSON in a new tab`"
              >
                Open JSON
                <UIcon name="i-lucide-arrow-up-right" class="size-3" />
              </a>
            </div>
          </div>
        </section>
      </div>
    </div>
  <BenchmarkGraphModal
    :open="graphModal.open"
    :eyebrow="graphModal.eyebrow"
    :title="graphModal.title"
    :description="graphModal.description"
    :source-href="graphModal.sourceHref"
    :summary="graphModal.summary"
    :columns="graphModal.tableColumns"
    :rows="graphModal.tableRows"
    :table-note="graphModal.tableNote"
    :selectable="graphModal.selectable"
    :active-row="graphModal.selectable ? activeModalRow : -1"
    :pinned-row="graphModal.selectable ? pinnedRow : -1"
    :selection-label="graphModal.selectionLabel"
    @preview="previewGraphRow"
    @select="selectGraphRow"
    @close="closeGraph"
  >
    <BenchmarkChart
      v-if="graphModal.chartKind === 'line'"
      :series="graphModal.lineSeries"
      :labels="graphModal.lineLabels"
      :width="isCompact ? 460 : 1040"
      :height="isCompact ? 260 : 260"
      :threshold="graphModal.threshold"
      :threshold-label="graphModal.thresholdLabel"
      :active-index="graphModal.activeIndex"
      :max-x-labels="isCompact ? 4 : 6"
      :compact="isCompact"
      :y-ticks="isCompact ? 3 : 4"
    />
    <BenchmarkBarChart
      v-else-if="graphModal.chartKind === 'bar'"
      :labels="graphModal.barLabels"
      :series="graphModal.barSeries"
      :width="isCompact ? 460 : 1040"
      :height="isCompact ? 260 : 260"
      :threshold="graphModal.threshold"
      :threshold-label="graphModal.thresholdLabel"
      :compact="isCompact"
      :y-ticks="graphModal.barYTicks ?? (isCompact ? 3 : 4)"
    />
    <BenchmarkMicrobenchChart
      v-else-if="graphModal.chartKind === 'list'"
      :items="graphModal.listItems"
      :compact="isCompact"
    />
    <BenchmarkMeter
      v-else
      :items="graphModal.meterItems"
      :threshold="graphModal.meterThreshold"
      :total="graphModal.meterTotal"
      class="mx-auto max-w-3xl"
    />
  </BenchmarkGraphModal>
  </div>
</template>
