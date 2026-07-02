(function () {
  globalThis.IBEXBench = {
    autoRefreshTimer: null,
    trendChart: null,
    waterfallChart: null,
    loadChart: null,
  };

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

  function goBenchMetrics(run) {
    return run.go_benchmarks?.BenchmarkProxyHealth ?? run.go_benchmarks?.BenchmarkProxyOverhead ?? {};
  }

  function wireControls(rerender) {
    const refreshBtn = document.querySelector("#refreshBtn");
    if (refreshBtn) refreshBtn.onclick = () => rerender();

    const autoBtn = document.querySelector("#autorefreshBtn");
    if (!autoBtn) return;
    autoBtn.onclick = () => toggleAutoRefresh(autoBtn, rerender);
  }

  function toggleAutoRefresh(button, rerender) {
    if (globalThis.IBEXBench.autoRefreshTimer) {
      clearInterval(globalThis.IBEXBench.autoRefreshTimer);
      globalThis.IBEXBench.autoRefreshTimer = null;
      button.textContent = "Auto Refresh: Off";
      return;
    }
    globalThis.IBEXBench.autoRefreshTimer = setInterval(rerender, 60000);
    button.textContent = "Auto Refresh: On (60s)";
  }

  function setLastUpdated(timestamp) {
    const target = document.querySelector("#lastUpdated");
    if (!target) return;
    target.textContent = `Last updated: ${timestamp ? new Date(timestamp).toLocaleString() : "n/a"}`;
  }

  function filterRunsBySha(runs, prefix) {
    const f = prefix.trim().toLowerCase();
    if (!f) return runs;
    return runs.filter((r) => (r.sha || "").toLowerCase().startsWith(f));
  }

  function toggleEmptyState(latest) {
    const empty = !latest;
    const emptyEl = document.querySelector("#empty");
    const contentEl = document.querySelector("#content");
    if (emptyEl) emptyEl.style.display = empty ? "block" : "none";
    if (contentEl) contentEl.style.display = empty ? "none" : "block";
    return empty;
  }

  function hasK6Signal(k6) {
    return (k6?.req_per_s || 0) > 0 && (k6?.p99_ms || 0) > 0;
  }

  function healthStatus(latest, policy) {
    const k6 = latest.k6 || {};
    if (!hasK6Signal(k6)) {
      return { label: "Regression Risk", className: "bad" };
    }
    const withinP99 = withinLimit(k6.p99_ms, policy.max_proxy_overhead_p99_ms, 20);
    const withinErr = withinLimit(k6.error_rate, policy.max_error_rate, 0.001);
    if (withinP99 && withinErr) {
      return { label: "Healthy", className: "good" };
    }
    return { label: "Regression Risk", className: "bad" };
  }

  function setTrendChart(buildChart) {
    const charts = globalThis.IBEXBenchCharts;
    if (!charts) return;
    charts.destroyChart(globalThis.IBEXBench.trendChart);
    globalThis.IBEXBench.trendChart = buildChart(charts);
  }

  function setLoadChart(buildChart) {
    const charts = globalThis.IBEXBenchCharts;
    if (!charts) return;
    charts.destroyChart(globalThis.IBEXBench.loadChart);
    globalThis.IBEXBench.loadChart = buildChart(charts);
  }

  function setWaterfallChart(buildChart) {
    const charts = globalThis.IBEXBenchCharts;
    if (!charts) return;
    charts.destroyChart(globalThis.IBEXBench.waterfallChart);
    globalThis.IBEXBench.waterfallChart = buildChart(charts);
  }

  Object.assign(globalThis.IBEXBench, {
    fetchRunsJson,
    fetchBaselineJson,
    pctOfBudget,
    tone,
    withinLimit,
    el,
    clearChildren,
    safeHref,
    formatMetricMs,
    formatAllocs,
    formatErrorRate,
    goBenchMetrics,
    wireControls,
    toggleAutoRefresh,
    setLastUpdated,
    filterRunsBySha,
    toggleEmptyState,
    healthStatus,
    setTrendChart,
    setLoadChart,
    setWaterfallChart,
  });
})();
