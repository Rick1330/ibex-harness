(function () {
  const NAV = [
    { id: "overview", href: "./index.html", label: "Overview" },
    { id: "trends", href: "./trends.html", label: "Trends" },
    { id: "waterfall", href: "./waterfall.html", label: "Waterfall" },
    { id: "load", href: "./load.html", label: "Load" },
    { id: "commits", href: "./commits.html", label: "Commits" },
  ];

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function buildNav(current) {
    const nav = el("nav", "site-nav-links");
    NAV.forEach((item) => {
      const link = document.createElement("a");
      link.href = item.href;
      link.textContent = item.label;
      if (item.id === current) link.classList.add("active");
      link.setAttribute("aria-current", item.id === current ? "page" : "false");
      nav.appendChild(link);
    });
    return nav;
  }

  function buildHeader(current, subtitle) {
    const header = el("header", "site-header");
    const inner = el("div", "site-header-inner");

    const brand = el("a", "site-brand");
    brand.href = "./index.html";
    brand.setAttribute("aria-label", "IBEX Harness benchmarks home");

    const markLight = document.createElement("img");
    markLight.src = "./brand/ibex-mark-light.png";
    markLight.alt = "";
    markLight.width = 28;
    markLight.height = 28;
    markLight.decoding = "async";
    markLight.className = "site-brand-mark site-brand-mark-light";
    brand.appendChild(markLight);

    const markDark = document.createElement("img");
    markDark.src = "./brand/ibex-mark-dark.png";
    markDark.alt = "";
    markDark.width = 28;
    markDark.height = 28;
    markDark.decoding = "async";
    markDark.className = "site-brand-mark site-brand-mark-dark";
    brand.appendChild(markDark);

    const wordmark = el("span", "site-wordmark");
    const ibex = el("span", "site-wordmark-primary", "ibex");
    const harness = el("span", "site-wordmark-secondary", "harness");
    wordmark.appendChild(ibex);
    wordmark.appendChild(harness);
    brand.appendChild(wordmark);

    const brandText = el("div", "site-brand-copy");
    brandText.appendChild(brand);
    if (subtitle) {
      brandText.appendChild(el("p", "site-subtitle", subtitle));
    }

    const actions = el("div", "site-header-actions");
    const themeBtn = el("button", "btn btn-ghost", "Theme");
    themeBtn.type = "button";
    themeBtn.setAttribute("aria-label", "Toggle light and dark theme");
    themeBtn.onclick = () => {
      const next = globalThis.IBEXBenchTheme.toggle();
      themeBtn.textContent = next === "dark" ? "Dark" : "Light";
    };
    themeBtn.textContent = globalThis.IBEXBenchTheme.get() === "dark" ? "Dark" : "Light";
    actions.appendChild(themeBtn);
    actions.appendChild(buildNav(current));

    inner.appendChild(brandText);
    inner.appendChild(actions);
    header.appendChild(inner);
    return header;
  }

  function mount() {
    const mountPoint = document.getElementById("site-header");
    if (!mountPoint) return;
    const page = document.body.dataset.page || "overview";
    const subtitle = document.body.dataset.subtitle || "Performance intelligence";
    const header = buildHeader(page, subtitle);
    mountPoint.replaceWith(header);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
