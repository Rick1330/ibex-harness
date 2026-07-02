(function () {
  const bench = () => globalThis.IBEXBench;

  function renderCard(title, value, meta, cls) {
    const card = bench().el("div", `card ${cls || "neutral"}`);
    card.appendChild(bench().el("h3", null, title));
    card.appendChild(bench().el("div", "value", value));
    card.appendChild(bench().el("div", "meta", meta));
    return card;
  }

  function appendTextCell(row, text) {
    row.appendChild(bench().el("td", null, text));
  }

  function appendRunLinkCell(row, url) {
    const cell = document.createElement("td");
    const link = document.createElement("a");
    link.href = bench().safeHref(url);
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = "run";
    cell.appendChild(link);
    row.appendChild(cell);
  }

  function appendRunRow(tbody, r) {
    const k6 = r.k6 || {};
    const row = document.createElement("tr");
    const shaCell = document.createElement("td");
    shaCell.appendChild(bench().el("code", null, (r.sha || "").slice(0, 8)));
    row.appendChild(shaCell);
    appendTextCell(row, new Date(r.timestamp).toLocaleString());
    appendTextCell(row, r.branch || "");
    appendTextCell(row, bench().formatMetricMs(k6.p99_ms));
    appendTextCell(row, bench().formatAllocs(r));
    appendTextCell(row, bench().formatErrorRate(k6.error_rate));
    appendRunLinkCell(row, r.run_url);
    tbody.appendChild(row);
  }

  function updateHealthBadge(latest, policy) {
    const badge = document.querySelector("#healthBadge");
    if (!badge || !latest) return;
    const status = bench().healthStatus(latest, policy);
    badge.textContent = status.label;
    badge.className = `status-badge ${status.className}`;
  }

  function appendMetaRow(container, label, valueNode) {
    const row = document.createElement("div");
    row.appendChild(bench().el("strong", null, `${label}: `));
    row.appendChild(valueNode);
    container.appendChild(row);
  }

  function viewModel(latest, policy) {
    const k6 = latest.k6 || {};
    const go = bench().goBenchMetrics(latest);
    const budget = policy.max_proxy_overhead_p99_ms ?? 20;
    const budgetPct = bench().pctOfBudget(k6.p99_ms || 0, budget);
    return { k6, go, budget, budgetPct };
  }

  function renderKpis(model, policy) {
    const { k6, go, budget, budgetPct } = model;
    const kpis = document.querySelector("#kpis");
    if (!kpis) return;
    bench().clearChildren(kpis);
    const errLimit = policy.max_error_rate ?? 0.001;
    const errOk = (k6.error_rate || 0) <= errLimit;
    kpis.appendChild(
      renderCard(
        "Proxy p99",
        `${(k6.p99_ms || 0).toFixed(2)} ms`,
        `${budgetPct.toFixed(1)}% of ${budget}ms budget`,
        bench().tone(budgetPct),
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
    bench().clearChildren(meta);
    appendMetaRow(meta, "Last run", bench().el("span", null, new Date(latest.timestamp).toLocaleString()));
    appendMetaRow(meta, "Commit", bench().el("code", null, latest.sha || "unknown"));
    appendMetaRow(meta, "Branch", bench().el("code", null, latest.branch || "main"));
    const runLink = document.createElement("a");
    runLink.href = bench().safeHref(latest.run_url);
    runLink.target = "_blank";
    runLink.rel = "noreferrer";
    runLink.textContent = latest.run_url || "n/a";
    appendMetaRow(meta, "Run", runLink);
    appendMetaRow(
      meta,
      "Runner",
      bench().el(
        "span",
        null,
        `${latest.runner || "unknown"} / ${latest.runner_cpu || "unknown"} / vCPU ${latest.runner_vcpus || "?"}`,
      ),
    );
    appendMetaRow(meta, "Go", bench().el("span", null, latest.go_version || "unknown"));
    appendMetaRow(meta, "Baseline", bench().el("code", null, baseline.target_commit || "unset"));
  }

  function formatStageLabel(name) {
    return name.replaceAll("_", " ");
  }

  function renderStages(latest) {
    const stages = document.querySelector("#stages");
    if (!stages) return;
    bench().clearChildren(stages);
    Object.entries(latest.stages || {}).forEach(([name, value]) => {
      const li = document.createElement("li");
      li.appendChild(bench().el("span", null, formatStageLabel(name)));
      li.appendChild(bench().el("strong", null, `${(value || 0).toFixed(3)} µs`));
      stages.appendChild(li);
    });
  }

  function renderRuns(runs) {
    const rowsRoot = document.querySelector("#runs tbody");
    if (!rowsRoot) return;
    bench().clearChildren(rowsRoot);
    runs.slice(0, 50).forEach((r) => appendRunRow(rowsRoot, r));
  }

  function wireHistoryFilter(runs) {
    const input = document.querySelector("#shaFilter");
    if (!input) return;
    input.oninput = () => renderRuns(bench().filterRunsBySha(runs, input.value));
  }

  function appendTrendRow(tbody, run) {
    const k = run.k6 || {};
    const g = bench().goBenchMetrics(run);
    const row = document.createElement("tr");
    const shaCell = bench().el("td");
    shaCell.appendChild(bench().el("code", null, (run.sha || "").slice(0, 8)));
    row.appendChild(shaCell);
    appendTextCell(row, new Date(run.timestamp).toLocaleString());
    appendTextCell(row, (k.p50_ms || 0).toFixed(2));
    appendTextCell(row, (k.p95_ms || 0).toFixed(2));
    appendTextCell(row, (k.p99_ms || 0).toFixed(2));
    appendTextCell(row, (k.p999_ms || 0).toFixed(2));
    appendTextCell(row, (k.req_per_s || 0).toFixed(0));
    appendTextCell(row, (g.allocs_per_op || 0).toFixed(2));
    appendTextCell(row, (g.bytes_per_op || 0).toFixed(0));
    tbody.appendChild(row);
  }

  function renderTrendChart(recent) {
    const canvas = document.getElementById("trendChart");
    if (!canvas) return;
    bench().updateChart("trendChart", (charts) =>
      charts.lineChart(
        canvas,
        recent.map((r) => (r.sha || "").slice(0, 8)),
        recent.map((r) => r.k6?.p99_ms || 0),
        "p99 (ms)",
      ),
    );
  }

  function renderTrends(runs) {
    const recent = runs.slice(0, 30).reverse();
    renderTrendChart(recent);
    const tbody = document.querySelector("#trendTable tbody");
    if (!tbody) return;
    bench().clearChildren(tbody);
    runs.forEach((run) => appendTrendRow(tbody, run));
  }

  function renderLoadTiles(root, k6) {
    const tiles = [
      ["p50", `${(k6.p50_ms || 0).toFixed(2)} ms`],
      ["p95", `${(k6.p95_ms || 0).toFixed(2)} ms`],
      ["p99", `${(k6.p99_ms || 0).toFixed(2)} ms`],
      ["p99.9", `${(k6.p999_ms || 0).toFixed(2)} ms`],
      ["throughput", `${(k6.req_per_s || 0).toFixed(0)} req/s`],
      ["error rate", `${((k6.error_rate || 0) * 100).toFixed(3)}%`],
      ["check rate", `${((k6.check_rate || 0) * 100).toFixed(2)}%`],
    ];
    tiles.forEach(([label, value]) => {
      const tile = bench().el("div", "metric-tile");
      tile.appendChild(bench().el("div", "label", label));
      tile.appendChild(bench().el("div", "num", value));
      root.appendChild(tile);
    });
  }

  function renderLoadChart(k6) {
    const canvas = document.getElementById("loadChart");
    if (!canvas) return;
    bench().updateChart("loadChart", (charts) =>
      charts.barChart(
        canvas,
        ["p50", "p95", "p99", "p99.9"],
        [k6.p50_ms || 0, k6.p95_ms || 0, k6.p99_ms || 0, k6.p999_ms || 0],
        "Latency (ms)",
      ),
    );
  }

  function renderLoad(latest) {
    const root = document.getElementById("loadMetrics");
    if (!root || !latest) return;
    const k6 = latest.k6 || {};
    bench().clearChildren(root);
    renderLoadTiles(root, k6);
    renderLoadChart(k6);
  }

  function renderWaterfall(latest) {
    const stages = latest?.stages || {};
    const labels = Object.keys(stages).map(formatStageLabel);
    const values = Object.values(stages).map((v) => Number(v) || 0);
    const canvas = document.getElementById("waterfallChart");
    if (!canvas) return;
    bench().updateChart("waterfallChart", (charts) =>
      charts.barChart(canvas, labels, values, "µs per op"),
    );
  }

  function showLoadEmpty() {
    const root = document.getElementById("loadMetrics");
    if (root) root.textContent = "No data.";
  }

  function showWaterfallEmpty() {
    const root = document.getElementById("waterfallChart");
    if (root) root.replaceWith(bench().el("p", "panel-note", "No data."));
  }

  async function bootOverview(runs, baselineWrap, rerender) {
    const latest = runs[0];
    const baseline = baselineWrap.baseline || {};
    const policy = baselineWrap.policy || {};
    if (bench().toggleEmptyState(latest)) return;
    const model = viewModel(latest, policy);
    bench().setLastUpdated(latest.timestamp);
    updateHealthBadge(latest, policy);
    renderKpis(model, policy);
    renderMeta(latest, baseline);
    renderStages(latest);
    bench().wireControls(rerender);
  }

  async function bootCommits(runs, rerender) {
    renderRuns(runs);
    wireHistoryFilter(runs);
    bench().wireControls(rerender);
  }

  async function bootTrends(runs, rerender) {
    renderTrends(runs);
    bench().wireControls(rerender);
  }

  async function bootLoad(latest, rerender) {
    if (!latest) {
      showLoadEmpty();
      return;
    }
    renderLoad(latest);
    bench().wireControls(rerender);
  }

  async function bootWaterfall(latest, rerender) {
    if (!latest) {
      showWaterfallEmpty();
      return;
    }
    renderWaterfall(latest);
    bench().wireControls(rerender);
  }

  const PAGE_BOOT = {
    overview: (runs, baselineWrap, latest, rerender) => bootOverview(runs, baselineWrap, rerender),
    commits: (runs, _baselineWrap, _latest, rerender) => bootCommits(runs, rerender),
    trends: (runs, _baselineWrap, _latest, rerender) => bootTrends(runs, rerender),
    load: (_runs, _baselineWrap, latest, rerender) => bootLoad(latest, rerender),
    waterfall: (_runs, _baselineWrap, latest, rerender) => bootWaterfall(latest, rerender),
  };

  async function boot() {
    const page = document.body.dataset.page || "overview";
    const runsWrap = await bench().fetchRunsJson();
    const baselineWrap = await bench().fetchBaselineJson();
    const runs = runsWrap.runs || [];
    const latest = runs[0];
    const handler = PAGE_BOOT[page] || PAGE_BOOT.overview;
    await handler(runs, baselineWrap, latest, boot);
  }

  globalThis.addEventListener("ibex-theme-change", () => boot());
  boot();
})();
