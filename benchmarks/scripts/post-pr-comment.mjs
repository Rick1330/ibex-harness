#!/usr/bin/env node
/**
 * Posts benchmark regression summary as a PR comment (GitHub Actions).
 * Requires: GITHUB_TOKEN, GITHUB_REPOSITORY, PR_NUMBER
 * Optional: BENCHMARK_DATA_PATH (must equal benchmarks/output/benchmark-data.json)
 */
import fs from "node:fs";
import process from "node:process";

const BENCHMARK_DATA_FILE = "benchmarks/output/benchmark-data.json";

const token = process.env.GITHUB_TOKEN;
const repo = process.env.GITHUB_REPOSITORY;
const prNumber = process.env.PR_NUMBER;
const dataPathEnv = process.env.BENCHMARK_DATA_PATH;

if (!token || !repo || !prNumber) {
  console.error("post-pr-comment: missing GITHUB_TOKEN, GITHUB_REPOSITORY, or PR_NUMBER");
  process.exit(1);
}

if (dataPathEnv && dataPathEnv !== BENCHMARK_DATA_FILE) {
  console.error("post-pr-comment: BENCHMARK_DATA_PATH must be benchmarks/output/benchmark-data.json");
  process.exit(1);
}

if (!fs.existsSync(BENCHMARK_DATA_FILE)) {
  console.error("post-pr-comment: data file not found");
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(BENCHMARK_DATA_FILE, "utf8"));
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

function markdownTableRow(cells) {
  return `| ${cells.join(" | ")} |`;
}

const resultsTable = [
  markdownTableRow(["Metric", "This run", "Delta vs baseline"]),
  markdownTableRow(["---", "---", "---"]),
  markdownTableRow(["Proxy p99", `${run.k6?.p99_ms ?? "—"}ms`, deltaText]),
  markdownTableRow(["Throughput", `${run.k6?.req_per_s ?? "—"} req/s`, "—"]),
  markdownTableRow(["Error rate", `${((run.k6?.error_rate ?? 0) * 100).toFixed(3)}%`, "—"]),
].join("\n");

const body = `## Benchmark Results — Run #${run.run_number ?? "?"}

**Status:** ${statusEmoji} ${String(run.status).toUpperCase()} | Commit: \`${run.short_sha}\` | [View dashboard →](https://docs.ibexharness.com/benchmarks/history/${run.short_sha})

${resultsTable}

> Regression threshold: >10% degradation on proxy p99 fails CI.`;

const [owner, name] = repo.split("/");
const controller = new AbortController();
const timeout = setTimeout(() => { controller.abort(); }, 10_000);
let response = null;
try {
  response = await fetch(
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
      signal: controller.signal,
    },
  );
} catch (error) {
  console.error("post-pr-comment: fetch failed", error);
  process.exit(1);
} finally {
  clearTimeout(timeout);
}

if (!response?.ok) {
  console.error(`post-pr-comment: GitHub API request failed with status ${response?.status ?? "unknown"}`);
  process.exit(1);
}

console.log("post-pr-comment: comment posted");
