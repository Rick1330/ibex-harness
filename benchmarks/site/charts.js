(function () {
  const CHART_DEFAULTS = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: "hsl(var(--panel-raised) / 0.96)",
        titleColor: "hsl(var(--text-primary))",
        bodyColor: "hsl(var(--text-secondary))",
        borderColor: "hsl(var(--border))",
        borderWidth: 1,
      },
    },
    scales: {
      x: {
        grid: { color: "hsl(var(--border) / 0.5)" },
        ticks: { color: "hsl(var(--text-tertiary))", maxTicksLimit: 8 },
      },
      y: {
        grid: { color: "hsl(var(--border) / 0.5)" },
        ticks: { color: "hsl(var(--text-tertiary))" },
      },
    },
  };

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function chartColors() {
    return {
      line: `hsl(${cssVar("--info")})`,
      fill: `hsl(${cssVar("--info")} / 0.12)`,
      good: `hsl(${cssVar("--success")})`,
      warn: `hsl(${cssVar("--warning")})`,
      bad: `hsl(${cssVar("--danger")})`,
      muted: `hsl(${cssVar("--text-tertiary")})`,
    };
  }

  function destroyChart(chart) {
    if (chart) chart.destroy();
  }

  function lineChart(canvas, labels, values, label) {
    if (!globalThis.Chart || !canvas) return null;
    const colors = chartColors();
    return new globalThis.Chart(canvas, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label,
            data: values,
            borderColor: colors.line,
            backgroundColor: colors.fill,
            fill: true,
            tension: 0.28,
            pointRadius: 2,
            pointHoverRadius: 4,
          },
        ],
      },
      options: {
        ...CHART_DEFAULTS,
        scales: {
          ...CHART_DEFAULTS.scales,
          y: {
            ...CHART_DEFAULTS.scales.y,
            title: { display: true, text: label, color: `hsl(${cssVar("--text-secondary")})` },
          },
        },
      },
    });
  }

  function barChart(canvas, labels, values, label) {
    if (!globalThis.Chart || !canvas) return null;
    const colors = chartColors();
    const max = Math.max(...values, 1);
    const bg = values.map((v) => {
      const ratio = v / max;
      if (ratio > 0.85) return colors.bad;
      if (ratio > 0.6) return colors.warn;
      return colors.good;
    });
    return new globalThis.Chart(canvas, {
      type: "bar",
      data: {
        labels,
        datasets: [{ label, data: values, backgroundColor: bg, borderRadius: 6 }],
      },
      options: {
        ...CHART_DEFAULTS,
        indexAxis: "y",
        scales: {
          x: {
            ...CHART_DEFAULTS.scales.x,
            title: { display: true, text: label, color: `hsl(${cssVar("--text-secondary")})` },
          },
          y: { ...CHART_DEFAULTS.scales.y, grid: { display: false } },
        },
      },
    });
  }

  globalThis.IBEXBenchCharts = { lineChart, barChart, destroyChart, chartColors };
})();
