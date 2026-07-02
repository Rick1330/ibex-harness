(function () {
  const bench = () => globalThis.IBEXBench;
  const pages = () => globalThis.IBEXBenchPages;

  async function bootPage(page, runs, baselineWrap, latest, rerender) {
    switch (page) {
      case "commits":
        return pages().bootCommits(runs, rerender);
      case "trends":
        return pages().bootTrends(runs, rerender);
      case "load":
        return pages().bootLoad(latest, rerender);
      case "waterfall":
        return pages().bootWaterfall(latest, rerender);
      default:
        return pages().bootOverview(runs, baselineWrap, rerender);
    }
  }

  async function boot() {
    const page = document.body.dataset.page || "overview";
    const runsWrap = await bench().fetchRunsJson();
    const baselineWrap = await bench().fetchBaselineJson();
    const runs = runsWrap.runs || [];
    const latest = runs[0];
    await bootPage(page, runs, baselineWrap, latest, boot);
  }

  globalThis.addEventListener("ibex-theme-change", () => boot());
  boot();
})();
