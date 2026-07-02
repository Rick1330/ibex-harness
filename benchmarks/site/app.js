(function () {
  let autoRefreshTimer = null;

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => {
      const map = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      };
      return map[ch];
    });
  }

  async function readJson(path, fallback) {
    try {
      const res = await fetch(path, { cache: "no-store" });
      if (!res.ok) return fallback;
      return await res.json();
    } catch (e) {
      console.warn("failed to fetch benchmark JSON", path, e);
      return fallback;
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

  function card(title, value, meta, cls) {
    return `<div class="card ${esc(cls)}"><h3>${esc(title)}</h3><div class="value">${esc(value)}</div><div class="meta">${esc(meta)}</div></div>`;
  }

  function runRow(r) {
    const k6 = r.k6 || {};
    return `<tr>
      <td><code>${esc((r.sha || "").slice(0, 8))}</code></td>
      <td>${new Date(r.timestamp).toLocaleString()}</td>
      <td>${esc(r.branch || "")}</td>
      <td>${(k6.p99_ms || 0).toFixed(2)} ms</td>
      <td>${r.go_benchmarks?.BenchmarkProxyOverhead?.allocs_per_op?.toFixed?.(2) || "0.00"}</td>
      <td>${(k6.error_rate || 0).toFixed(4)}</td>
      <td><a href="${esc(r.run_url || "#")}" target="_blank" rel="noreferrer">run</a></td>
    </tr>`;
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
    const p99Ok = p99 <= (policy.max_proxy_overhead_p99_ms || 20);
    const errOk = err <= (policy.max_error_rate || 0.001);
    if (p99Ok && errOk) {
      return { label: "Healthy", borderColor: "#22c55e" };
    }
    return { label: "Regression Risk", borderColor: "#ef4444" };
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
    autoBtn.onclick = () => {
      if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
        autoRefreshTimer = null;
        autoBtn.textContent = "Auto Refresh: Off";
        return;
      }
      autoRefreshTimer = setInterval(rerender, 60000);
      autoBtn.textContent = "Auto Refresh: On (60s)";
    };
  }

  function setLastUpdated(timestamp) {
    const target = document.querySelector("#lastUpdated");
    if (!target) return;
    target.textContent = `Last updated: ${timestamp ? new Date(timestamp).toLocaleString() : "n/a"}`;
  }

  function wireHistoryFilter(runs) {
    const input = document.querySelector("#shaFilter");
    const rowsRoot = document.querySelector("#runs tbody");
    if (!input || !rowsRoot) return;
    input.addEventListener("input", () => {
      const f = input.value.trim().toLowerCase();
      const filtered = f ? runs.filter((r) => (r.sha || "").toLowerCase().startsWith(f)) : runs;
      rowsRoot.innerHTML = filtered.slice(0, 50).map(runRow).join("");
    });
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
    const budget = policy.max_proxy_overhead_p99_ms || 20;
    const budgetPct = pctOfBudget(k6.p99_ms || 0, budget);
    return { k6, go, budget, budgetPct };
  }

  function renderKpis(model, policy) {
    const { k6, go, budget, budgetPct } = model;
    const kpis = document.querySelector("#kpis");
    if (!kpis) return;
    kpis.innerHTML = [
      card("Proxy p99", `${(k6.p99_ms || 0).toFixed(2)} ms`, `${budgetPct.toFixed(1)}% of ${budget}ms budget`, tone(budgetPct)),
      card("Throughput", `${(k6.req_per_s || 0).toFixed(0)} req/s`, "k6 http_reqs rate", "neutral"),
      card("Allocs/op", `${(go.allocs_per_op || 0).toFixed(2)}`, `${(go.bytes_per_op || 0).toFixed(0)} B/op`, "neutral"),
      card("Error rate", `${((k6.error_rate || 0) * 100).toFixed(3)}%`, `target < ${(policy.max_error_rate || 0.001) * 100}%`, (k6.error_rate || 0) <= (policy.max_error_rate || 0.001) ? "good" : "bad"),
    ].join("");
  }

  function renderMeta(latest, baseline) {
    const meta = document.querySelector("#meta");
    if (!meta) return;
    meta.innerHTML = `
      <div><strong>Last run:</strong> ${esc(new Date(latest.timestamp).toLocaleString())}</div>
      <div><strong>Commit:</strong> <code>${esc(latest.sha)}</code></div>
      <div><strong>Branch:</strong> <code>${esc(latest.branch || "main")}</code></div>
      <div><strong>Run:</strong> <a href="${esc(latest.run_url || "#")}" target="_blank" rel="noreferrer">${esc(latest.run_url || "n/a")}</a></div>
      <div><strong>Runner:</strong> ${esc(latest.runner || "unknown")} / ${esc(latest.runner_cpu || "unknown")} / vCPU ${esc(latest.runner_vcpus || "?")}</div>
      <div><strong>Go:</strong> ${esc(latest.go_version || "unknown")}</div>
      <div><strong>Baseline:</strong> <code>${esc(baseline.target_commit || "unset")}</code></div>
    `;
  }

  function renderStages(latest) {
    const stages = document.querySelector("#stages");
    if (!stages) return;
    stages.innerHTML = Object.entries(latest.stages || {})
      .map(([k, v]) => `<li><span>${esc(k)}</span><strong>${(v || 0).toFixed(3)} ms</strong></li>`)
      .join("");
  }

  function renderRuns(runs) {
    const rowsRoot = document.querySelector("#runs tbody");
    if (!rowsRoot) return;
    rowsRoot.innerHTML = runs.slice(0, 50).map(runRow).join("");
  }

  async function boot() {
    setActiveNav();
    const runsWrap = await readJson("./data/runs.json", { runs: [] });
    const baselineWrap = await readJson("./data/baseline.json", {});
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
