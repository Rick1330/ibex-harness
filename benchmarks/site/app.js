(function () {
  let autoRefreshTimer = null;
  let trendChart = null;
  let waterfallChart = null;
  let loadChart = null;

  async function fetchRunsJson() {
    try {
      const res = await fetch("./data/runs.json", { cache: "no-store" });
      if (!res.ok) return { runs: [] };
      return await res.json();
    } catch (e) {
      console.warn("failed to fetch runs.json", e);
      return { runs: [] };
    }
  }

  async function fetchBaselineJson() {
    try {
      const res = await fetch("./data/baseline.json", { cache: "no-store" });
      if (!res.ok) return {};
      return await res.json();
    } catch (e) {
      console.warn("failed to fetch baseline.json", e);
      return {};
    }
  }

  function pctOfBudget(v, budget) {
    if (!budget) return 0;
    return (v / budget) * 100;
  }

  function tone(pct) {
    if (pct < 70) return "good";
    if (pct < 90) return "warn";
    return "bad";
  }

  function withinLimit(value, limit, fallback) {
    return value <= (limit ?? fallback);
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function clearChildren(node) {
    while (node.firstChild) node.firstChild.remove();
  }

  function safeHref(url) {
    if (!url || url === "#") return "#";
    try {
      const parsed = new URL(url);
      if (parsed.protocol === "http:" || parsed.protocol === "https:") {
        return parsed.href;
      }
    } catch (e) {
      console.warn("invalid run URL", url, e);
    }
    return "#";
  }

  function renderCard(title, value, meta, cls) {
    const card = el("div", `card ${cls || "neutral"}`);
    card.appendChild(el("h3", null, title));
    card.appendChild(el("div", "value", value));
    card.appendChild(el("div", "meta", meta));
    return card;
  }

  function appendTextCell(row, text) {
    row.appendChild(el("td", null, text));
  }

  function appendRunLinkCell(row, url) {
    const cell = document.createElement("td");
    const link = document.createElement("a");
    link.href = safeHref(url);
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = "run";
    cell.appendChild(link);
    row.appendChild(cell);
  }

  function formatMetricMs(value) {
    return `${(value || 0).toFixed(2)} ms`;
  }

  function formatAllocs(run) {
    const proxy = run.go_benchmarks?.BenchmarkProxyHealth;
    const synthetic = run.go_benchmarks?.BenchmarkProxyOverhead;
    const allocs = proxy?.allocs_per_op ?? synthetic?.allocs_per_op;
    return allocs?.toFixed?.(2) || "0.00";
  }

  function formatErrorRate(value) {
    return (value || 0).toFixed(4);
  }

  function appendRunRow(tbody, r) {
    const k6 = r.k6 || {};
    const row = document.createElement("tr");
    const shaCell = document.createElement("td");
    shaCell.appendChild(el("code", null, (r.sha || "").slice(0, 8)));
    row.appendChild(shaCell);
    appendTextCell(row, new Date(r.timestamp).toLocaleString());
    appendTextCell(row, r.branch || "");
    appendTextCell(row, formatMetricMs(k6.p99_ms));
    appendTextCell(row, formatAllocs(r));
    appendTextCell(row, formatErrorRate(k6.error_rate));
    appendRunLinkCell(row, r.run_url);
    tbody.appendChild(row);
  }

  function healthStatus(latest, policy) {
    const p99 = latest.k6?.p99_ms || 0;
    const err = latest.k6?.error_rate || 0;
    const throughput = latest.k6?.req_per_s || 0;
    const healthy =
      throughput > 0 &&
      p99 > 0 &&
      withinLimit(p99, policy.max_proxy_overhead_p99_ms, 20) &&
      withinLimit(err, policy.max_error_rate, 0.001);
    return healthy
      ? { label: "Healthy", className: "good" }
      : { label: "Regression Risk", className: "bad" };
  }

  function updateHealthBadge(latest, policy) {
    const badge = document.querySelector("#healthBadge");
    if (!badge || !latest) return;
    const status = healthStatus(latest, policy);
    badge.textContent = status.label;
    badge.className = `status-badge ${status.className}`;
  }

  function wireControls(rerender) {
    const refreshBtn = document.querySelector("#refreshBtn");
    if (refreshBtn) refreshBtn.onclick = () => rerender();

    const autoBtn = document.querySelector("#autorefreshBtn");
    if (!autoBtn) return;
    autoBtn.onclick = () => toggleAutoRefresh(autoBtn, rerender);
  }

  function toggleAutoRefresh(button, rerender) {
    if (autoRefreshTimer) {
      clearInterval(autoRefreshTimer);
      autoRefreshTimer = null;
      button.textContent = "Auto Refresh: Off";
      return;
    }
    autoRefreshTimer = setInterval(rerender, 60000);
    button.textContent = "Auto Refresh: On (60s)";
  }

  function setLastUpdated(timestamp) {
    const target = document.querySelector("#lastUpdated");
    if (!target) return;
    target.textContent = `Last updated: ${timestamp ? new Date(timestamp).toLocaleString() : "n/a"}`;
  }

  function appendMetaRow(container, label, valueNode) {
    const row = document.createElement("div");
    row.appendChild(el("strong", null, `${label}: `));
    row.appendChild(valueNode);
    container.appendChild(row);
  }

  function filterRunsBySha(runs, prefix) {
    const f = prefix.trim().toLowerCase();
    if (!f) return runs;
    return runs.filter((r) => (r.sha || "").toLowerCase().startsWith(f));
  }

  function wireHistoryFilter(runs) {
    const input = document.querySelector("#shaFilter");
    if (!input) return;
    input.oninput = () => renderRuns(filterRunsBySha(runs, input.value));
  }

  function toggleEmptyState(latest) {
    const empty = !latest;
    const emptyEl = document.querySelector("#empty");
    const contentEl = document.querySelector("#content");
    if (emptyEl) emptyEl.style.display = empty ? "block" : "none";
    if (contentEl) contentEl.style.display = empty ? "none" : "block";
    return empty;
  }

  function viewModel(latest, policy) {
    const k6 = latest.k6 || {};
    const go = latest.go_benchmarks?.BenchmarkProxyHealth || latest.go_benchmarks?.BenchmarkProxyOverhead || {};
    const budget = policy.max_proxy_overhead_p99_ms ?? 20;
    const budgetPct = pctOfBudget(k6.p99_ms || 0, budget);
    return { k6, go, budget, budgetPct };
  }

  function renderKpis(model, policy) {
    const { k6, go, budget, budgetPct } = model;
    const kpis = document.querySelector("#kpis");
    if (!kpis) return;
    clearChildren(kpis);
    const errLimit = policy.max_error_rate ?? 0.001;
    const errOk = (k6.error_rate || 0) <= errLimit;
    kpis.appendChild(
      renderCard(
        "Proxy p99",
        `${(k6.p99_ms || 0).toFixed(2)} ms`,
        `${budgetPct.toFixed(1)}% of ${budget}ms budget`,
        tone(budgetPct),
      ),
    );
    kpis.appendChild(
      renderCard("Throughput", `${(k6.req_per_s || 0).toFixed(0)} req/s`, "k6 /health load test", "neutral"),
    );
    kpis.appendChild(
      renderCard(
        "Proxy /health",
        `${((go.ns_per_op || 0) / 1000).toFixed(2)} µs/op`,
        `${(go.allocs_per_op || 0).toFixed(2)} allocs · ${(go.bytes_per_op || 0).toFixed(0)} B/op`,
        "neutral",
      ),
    );
    kpis.appendChild(
      renderCard(
        "Error rate",
        `${((k6.error_rate || 0) * 100).toFixed(3)}%`,
        `target < ${errLimit * 100}%`,
        errOk ? "good" : "bad",
      ),
    );
  }

  function renderMeta(latest, baseline) {
    const meta = document.querySelector("#meta");
    if (!meta) return;
    clearChildren(meta);

    appendMetaRow(meta, "Last run", el("span", null, new Date(latest.timestamp).toLocaleString()));
    appendMetaRow(meta, "Commit", el("code", null, latest.sha || "unknown"));
    appendMetaRow(meta, "Branch", el("code", null, latest.branch || "main"));

    const runLink = document.createElement("a");
    runLink.href = safeHref(latest.run_url);
    runLink.target = "_blank";
    runLink.rel = "noreferrer";
    runLink.textContent = latest.run_url || "n/a";
    appendMetaRow(meta, "Run", runLink);

    appendMetaRow(
      meta,
      "Runner",
      el(
        "span",
        null,
        `${latest.runner || "unknown"} / ${latest.runner_cpu || "unknown"} / vCPU ${latest.runner_vcpus || "?"}`,
      ),
    );
    appendMetaRow(meta, "Go", el("span", null, latest.go_version || "unknown"));
    appendMetaRow(meta, "Baseline", el("code", null, baseline.target_commit || "unset"));
  }

  function formatStageLabel(name) {
    return name.replaceAll("_", " ");
  }

  function renderStages(latest) {
    const stages = document.querySelector("#stages");
    if (!stages) return;
    clearChildren(stages);
    Object.entries(latest.stages || {}).forEach(([name, value]) => {
      const li = document.createElement("li");
      li.appendChild(el("span", null, formatStageLabel(name)));
      li.appendChild(el("strong", null, `${(value || 0).toFixed(3)} µs`));
      stages.appendChild(li);
    });
  }

  function renderRuns(runs) {
    const rowsRoot = document.querySelector("#runs tbody");
    if (!rowsRoot) return;
    clearChildren(rowsRoot);
    runs.slice(0, 50).forEach((r) => appendRunRow(rowsRoot, r));
  }

  function renderTrends(runs) {
    const recent = runs.slice(0, 30).reverse();
    const canvas = document.getElementById("trendChart");
    if (canvas && globalThis.IBEXBenchCharts) {
      globalThis.IBEXBenchCharts.destroyChart(trendChart);
      trendChart = globalThis.IBEXBenchCharts.lineChart(
        canvas,
        recent.map((r) => (r.sha || "").slice(0, 8)),
        recent.map((r) => r.k6?.p99_ms || 0),
        "p99 (ms)",
      );
    }

    const tbody = document.querySelector("#trendTable tbody");
    if (!tbody) return;
    clearChildren(tbody);
    runs.forEach((r) => {
      const k = r.k6 || {};
      const g = r.go_benchmarks?.BenchmarkProxyHealth ?? r.go_benchmarks?.BenchmarkProxyOverhead ?? {};
      const row = document.createElement("tr");
      const shaCell = el("td");
      shaCell.appendChild(el("code", null, (r.sha || "").slice(0, 8)));
      row.appendChild(shaCell);
      appendTextCell(row, new Date(r.timestamp).toLocaleString());
      appendTextCell(row, (k.p50_ms || 0).toFixed(2));
      appendTextCell(row, (k.p95_ms || 0).toFixed(2));
      appendTextCell(row, (k.p99_ms || 0).toFixed(2));
      appendTextCell(row, (k.p999_ms || 0).toFixed(2));
      appendTextCell(row, (k.req_per_s || 0).toFixed(0));
      appendTextCell(row, (g.allocs_per_op || 0).toFixed(2));
      appendTextCell(row, (g.bytes_per_op || 0).toFixed(0));
      tbody.appendChild(row);
    });
  }

  function renderLoad(latest) {
    const root = document.getElementById("loadMetrics");
    if (!root || !latest) return;
    const k = latest.k6 || {};
    clearChildren(root);
    const tiles = [
      ["p50", `${(k.p50_ms || 0).toFixed(2)} ms`],
      ["p95", `${(k.p95_ms || 0).toFixed(2)} ms`],
      ["p99", `${(k.p99_ms || 0).toFixed(2)} ms`],
      ["p99.9", `${(k.p999_ms || 0).toFixed(2)} ms`],
      ["throughput", `${(k.req_per_s || 0).toFixed(0)} req/s`],
      ["error rate", `${((k.error_rate || 0) * 100).toFixed(3)}%`],
      ["check rate", `${((k.check_rate || 0) * 100).toFixed(2)}%`],
    ];
    tiles.forEach(([label, value]) => {
      const tile = el("div", "metric-tile");
      tile.appendChild(el("div", "label", label));
      tile.appendChild(el("div", "num", value));
      root.appendChild(tile);
    });

    const canvas = document.getElementById("loadChart");
    if (canvas && globalThis.IBEXBenchCharts) {
      globalThis.IBEXBenchCharts.destroyChart(loadChart);
      loadChart = globalThis.IBEXBenchCharts.barChart(
        canvas,
        ["p50", "p95", "p99", "p99.9"],
        [k.p50_ms || 0, k.p95_ms || 0, k.p99_ms || 0, k.p999_ms || 0],
        "Latency (ms)",
      );
    }
  }

  function renderWaterfall(latest) {
    const stages = latest?.stages || {};
    const labels = Object.keys(stages).map(formatStageLabel);
    const values = Object.values(stages).map((v) => Number(v) || 0);
    const canvas = document.getElementById("waterfallChart");
    if (canvas && globalThis.IBEXBenchCharts) {
      globalThis.IBEXBenchCharts.destroyChart(waterfallChart);
      waterfallChart = globalThis.IBEXBenchCharts.barChart(canvas, labels, values, "µs per op");
    }
  }

  async function bootOverview(runs, baselineWrap) {
    const latest = runs[0];
    const baseline = baselineWrap.baseline || {};
    const policy = baselineWrap.policy || {};
    if (toggleEmptyState(latest)) return;

    const model = viewModel(latest, policy);
    setLastUpdated(latest.timestamp);
    updateHealthBadge(latest, policy);
    renderKpis(model, policy);
    renderMeta(latest, baseline);
    renderStages(latest);
    wireControls(boot);
  }

  async function bootCommits(runs) {
    renderRuns(runs);
    wireHistoryFilter(runs);
    wireControls(boot);
  }

  async function boot() {
    const page = document.body.dataset.page || "overview";
    const runsWrap = await fetchRunsJson();
    const baselineWrap = await fetchBaselineJson();
    const runs = runsWrap.runs || [];
    const latest = runs[0];

    if (page === "overview") return bootOverview(runs, baselineWrap);
    if (page === "commits") return bootCommits(runs);
    if (page === "trends") {
      renderTrends(runs);
      wireControls(boot);
      return;
    }
    if (page === "load") {
      if (!latest) {
        const root = document.getElementById("loadMetrics");
        if (root) root.textContent = "No data.";
        return;
      }
      renderLoad(latest);
      wireControls(boot);
      return;
    }
    if (page === "waterfall") {
      if (!latest) {
        const root = document.getElementById("waterfallChart");
        if (root) root.replaceWith(el("p", "panel-note", "No data."));
        return;
      }
      renderWaterfall(latest);
      wireControls(boot);
    }
  }

  globalThis.addEventListener("ibex-theme-change", () => boot());
  boot();
})();
