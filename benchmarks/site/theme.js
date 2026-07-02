(function () {
  const STORAGE_KEY = "ibex-bench-theme";

  function preferredTheme() {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
    return globalThis.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
  }

  applyTheme(preferredTheme());

  globalThis.IBEXBenchTheme = {
    get() {
      return document.documentElement.dataset.theme || "dark";
    },
    set(theme) {
      if (theme !== "light" && theme !== "dark") return;
      localStorage.setItem(STORAGE_KEY, theme);
      applyTheme(theme);
      globalThis.dispatchEvent(new CustomEvent("ibex-theme-change", { detail: { theme } }));
    },
    toggle() {
      const next = this.get() === "dark" ? "light" : "dark";
      this.set(next);
      return next;
    },
  };
})();
