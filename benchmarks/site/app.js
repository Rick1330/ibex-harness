(function () {
  let autoRefreshTimer = null;

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
    const allocs = run.go_benchmarks?.BenchmarkProxyOverhead?.allocs_per_op;
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

  function setActiveNav() {
    const page = globalThis.location.pathname.split("/").pop() || "index.html";
    document.querySelectorAll("nav a").forEach((a) => {
      const href = a.getAttribute("href") || "";
      if (href.endsWith(page)) a.classList.add("active");
    });
  }

  function healthStatus(latest, policy) {
    const p99 = latest.k6?.p99_ms || 0;
    const err = latest.k6?.error_rate || 0;
    const healthy =
      withinLimit(p99, policy.max_proxy_overhead_p99_ms, 20) &&
      withinLimit(err, policy.max_error_rate, 0.001);
    return healthy
      ? { label: "Healthy", borderColor: "#22c55e" }
      : { label: "Regression Risk", borderColor: "#ef4444" };
  }

  function updateHealthBadge(latest, policy) {
    const badge = document.querySelector("#healthBadge");
    if (!badge || !latest) return;
    const status = healthStatus(latest, policy);
    badge.textContent = status.label;
    badge.style.borderColor = status.borderColor;
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
    const go = latest.go_benchmarks?.BenchmarkProxyOverhead || {};
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
      renderCard("Throughput", `${(k6.req_per_s || 0).toFixed(0)} req/s`, "k6 http_reqs rate", "neutral"),
    );
    kpis.appendChild(
      renderCard(
        "Allocs/op",
        `${(go.allocs_per_op || 0).toFixed(2)}`,
        `${(go.bytes_per_op || 0).toFixed(0)} B/op`,
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

  function renderStages(latest) {
    const stages = document.querySelector("#stages");
    if (!stages) return;
    clearChildren(stages);
    Object.entries(latest.stages || {}).forEach(([name, value]) => {
      const li = document.createElement("li");
      li.appendChild(el("span", null, name));
      li.appendChild(el("strong", null, `${(value || 0).toFixed(3)} ms`));
      stages.appendChild(li);
    });
  }

  function renderRuns(runs) {
    const rowsRoot = document.querySelector("#runs tbody");
    if (!rowsRoot) return;
    clearChildren(rowsRoot);
    runs.slice(0, 50).forEach((r) => appendRunRow(rowsRoot, r));
  }

  async function boot() {
    setActiveNav();
    const runsWrap = await fetchRunsJson();
    const baselineWrap = await fetchBaselineJson();
    const runs = runsWrap.runs || [];
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
    renderRuns(runs);
    wireHistoryFilter(runs);
    wireControls(boot);
  }

  boot();
})();
