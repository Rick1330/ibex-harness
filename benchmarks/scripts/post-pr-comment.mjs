#!/usr/bin/env node
/**
 * Posts benchmark regression summary as a PR comment (GitHub Actions).
 * Requires: GITHUB_TOKEN, GITHUB_REPOSITORY, PR_NUMBER, BENCHMARK_DATA_PATH
 */
import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const ALLOWED_OUTPUT_DIR = path.resolve("benchmarks/output");
const DEFAULT_DATA_PATH = path.join(ALLOWED_OUTPUT_DIR, "benchmark-data.json");

const token = process.env.GITHUB_TOKEN;
const repo = process.env.GITHUB_REPOSITORY;
const prNumber = process.env.PR_NUMBER;
const dataPathEnv = process.env.BENCHMARK_DATA_PATH ?? DEFAULT_DATA_PATH;

function resolveBenchmarkDataPath(inputPath) {
  const resolved = path.resolve(inputPath);
  if (!resolved.startsWith(ALLOWED_OUTPUT_DIR)) {
    console.error("post-pr-comment: benchmark data path must stay under benchmarks/output");
    process.exit(1);
  }
  return resolved;
}

if (!token || !repo || !prNumber) {
  console.error("post-pr-comment: missing GITHUB_TOKEN, GITHUB_REPOSITORY, or PR_NUMBER");
  process.exit(1);
}

const dataPath = resolveBenchmarkDataPath(dataPathEnv);

if (!fs.existsSync(dataPath)) {
  console.error("post-pr-comment: data file not found");
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(dataPath, "utf8"));
const run = data.runs?.[0];
if (!run) {
  console.error("post-pr-comment: no runs in benchmark data");
  process.exit(1);
}

function emojiForStatus(status) {
  if (status === "pass") {
    return "✅";
  }
  if (status === "regression") {
    return "⚠️";
  }
  return "❌";
}

function formatDelta(delta) {
  if (typeof delta !== "number") {
    return "n/a";
  }
  const sign = delta > 0 ? "+" : "";
  return `${sign}${delta.toFixed(1)}%`;
}

const statusEmoji = emojiForStatus(run.status);
const delta = run.regression_vs_baseline_pct;
const deltaText = formatDelta(delta);

const body = `## Benchmark Results — Run #${run.run_number ?? "?"}

**Status:** ${statusEmoji} ${String(run.status).toUpperCase()} | Commit: \`${run.short_sha}\` | [View dashboard →](https://docs.ibexharness.com/benchmarks/history/${run.short_sha})

| Metric | This run | Delta vs baseline |
| --- | --- | --- |
| Proxy p99 | ${run.k6?.p99_ms ?? "—"}ms | ${deltaText} |
| Throughput | ${run.k6?.req_per_s ?? "—"} req/s | — |
| Error rate | ${((run.k6?.error_rate ?? 0) * 100).toFixed(3)}% | — |

> Regression threshold: >10% degradation on proxy p99 fails CI.`;

const [owner, name] = repo.split("/");
const response = await fetch(
  `https://api.github.com/repos/${owner}/${name}/issues/${prNumber}/comments`,
  {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "Content-Type": "application/json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({ body }),
  },
);

if (!response.ok) {
  console.error(`post-pr-comment: GitHub API request failed with status ${response.status}`);
  process.exit(1);
}

console.log("post-pr-comment: comment posted");
