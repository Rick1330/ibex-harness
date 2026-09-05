import type { SuiteColumnId, SuiteLatestSnapshot } from "@/lib/benchmarks/cross-suite-compare";
import { formatMs, formatSuitePct } from "@/lib/benchmarks/format";
import { formatRecallPct } from "@/lib/benchmarks/hnsw-runs";

type IdentityFields = Readonly<{
  shortSha: string | null;
  status: string | null;
  timestamp: string | null;
}>;

function identityFrom(latest: {
  short_sha?: string;
  status?: string | null;
  timestamp?: string;
} | null | undefined): IdentityFields {
  return {
    shortSha: latest?.short_sha ?? null,
    status: latest?.status ?? null,
    timestamp: latest?.timestamp ?? null,
  };
}

function snapshot(
  id: SuiteColumnId,
  label: string,
  identity: IdentityFields,
  metrics: SuiteLatestSnapshot["metrics"],
): SuiteLatestSnapshot {
  return { id, label, ...identity, metrics };
}

export function proxySnapshot(latest: {
  short_sha: string;
  status?: string | null;
  timestamp: string;
  k6: { p99_ms: number; req_per_s: number };
  stages: { total_overhead_p99_ms: number };
} | null): SuiteLatestSnapshot {
  return snapshot("proxy", "Proxy", identityFrom(latest), latest
    ? [
        { label: "Proxy p99", value: formatMs(latest.k6.p99_ms) },
        { label: "Throughput", value: `${latest.k6.req_per_s.toFixed(0)} req/s` },
        {
          label: "Total overhead p99",
          value: formatMs(latest.stages.total_overhead_p99_ms),
        },
      ]
    : []);
}

export function hnswSnapshot(latest: {
  short_sha: string;
  status?: string | null;
  timestamp: string;
  mean_recall_at_10: number;
} | null): SuiteLatestSnapshot {
  return snapshot("hnsw", "HNSW", identityFrom(latest), latest
    ? [{ label: "Mean recall@10", value: formatRecallPct(latest.mean_recall_at_10) }]
    : []);
}

export function rankingSnapshot(latest: {
  short_sha: string;
  status?: string | null;
  timestamp: string;
  metrics: { precision_at_5: number; recall_at_10: number; mrr: number };
} | null): SuiteLatestSnapshot {
  return snapshot("rankingQuality", "Ranking", identityFrom(latest), latest
    ? [
        { label: "Precision@5", value: formatSuitePct(latest.metrics.precision_at_5) },
        { label: "Recall@10", value: formatSuitePct(latest.metrics.recall_at_10) },
        { label: "MRR", value: formatSuitePct(latest.metrics.mrr) },
      ]
    : []);
}

export function writeSnapshot(latest: {
  short_sha: string;
  status?: string | null;
  timestamp: string;
  metrics: { latency_ms_p95: number; latency_ms_p99: number };
} | null): SuiteLatestSnapshot {
  return snapshot("writePipeline", "Write", identityFrom(latest), latest
    ? [
        { label: "Write p95", value: formatMs(latest.metrics.latency_ms_p95) },
        { label: "Write p99", value: formatMs(latest.metrics.latency_ms_p99) },
      ]
    : []);
}

export function extractionSnapshot(latest: {
  short_sha: string;
  status?: string | null;
  timestamp: string;
  metrics: { precision_macro: number; recall_macro: number };
} | null): SuiteLatestSnapshot {
  return snapshot("extractionQuality", "Extraction", identityFrom(latest), latest
    ? [
        { label: "Precision macro", value: formatSuitePct(latest.metrics.precision_macro) },
        { label: "Recall macro", value: formatSuitePct(latest.metrics.recall_macro) },
      ]
    : []);
}
