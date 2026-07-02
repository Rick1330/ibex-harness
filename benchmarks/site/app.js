(function () {
  const bench = () => globalThis.IBEXBench;
  const pages = () => globalThis.IBEXBenchPages;

  function bootPage(ctx) {
    switch (ctx.page) {
      case "commits":
        return pages().bootCommits(ctx.runs, ctx.rerender);
      case "trends":
        return pages().bootTrends(ctx.runs, ctx.rerender);
      case "load":
        return pages().bootLoad(ctx.latest, ctx.rerender);
      case "waterfall":
        return pages().bootWaterfall(ctx.latest, ctx.rerender);
      default:
        return pages().bootOverview(ctx.runs, ctx.baselineWrap, ctx.rerender);
    }
  }

  async function boot() {
    const page = document.body.dataset.page || "overview";
    const runsWrap = await bench().fetchRunsJson();
    const baselineWrap = await bench().fetchBaselineJson();
    const runs = runsWrap.runs || [];
    const latest = runs[0];
    await bootPage({ page, runs, baselineWrap, latest, rerender: boot });
  }

  function safeBoot() {
    boot().catch((err) => {
      console.warn("benchmark dashboard boot failed", err);
    });
  }

  globalThis.addEventListener("ibex-theme-change", safeBoot);
  safeBoot();
})();
