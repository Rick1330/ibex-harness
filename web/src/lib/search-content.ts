type SearchTocItem = {
  title?: unknown;
  children?: SearchTocItem[];
};

export type SearchablePageData = {
  title?: string;
  description?: string;
  excerpt?: string;
  tags?: string[];
  toc?: SearchTocItem[];
  structuredData?: {
    contents?: Array<{ content?: string; heading?: string }>;
    headings?: Array<{ content?: string }>;
  };
};

export type SearchablePage = {
  url: string;
  data: SearchablePageData;
};

const STRUCTURED_CONTENT_CAP = 800;

// Dense decision/register pages stay directly accessible while using bounded
// summaries in the static token index to retain useful discoverability.
const COMPACT_SEARCH_SUMMARIES: Record<string, string> = {
  "/docs/adr/0081-fail-closed-proxy-runtime-controls":
    "Explicit Proxy IBEX_ENV profile; shared Redis is required outside development. Redis rate-limit outage returns 503 SERVICE_DEGRADED and blocks provider work, not 429. Model routing never bypasses organization policy; unavailable policy dependencies return 503, an ordinary policy denial is 403, exhausted quota is 429, and an unconfigured provider is 501. Development may use the Noop limiter. Staging and production require the Redis Secret.",
  "/roadmap/phase-4-multi-provider/findings":
    "Phase 4 multi-provider findings register: F4-015 model-policy Postgres failure must fail closed with 503, not permit all models or misreport 403; F4-034 Python and Semgrep CI gates must be required and enforce active-child applicability; F4-036 Proxy IBEX_ENV must be explicit in loader, Config.ApplyDefaults, and Helm; F4-037 shared Redis rate-limit outage must return 503 before provider work. P0/P1 findings remain open until merged and runtime/evidence gates pass.",
  "/roadmap/phase-4-multi-provider/risks":
    "Phase 4 operational risk register: console preview fixtures are not a live operator platform; tenant isolation, session authorization, policy-store availability, Redis rate limiting, Proxy runtime profiles, data retention/deletion, cost reconciliation, deployment secrets, recovery, and release evidence each have independent closure gates. Fail closed on policy/Redis dependency loss; verify explicit staging/production IBEX_ENV, provisioned Redis Secret health, live branch protection, and deployed rollback evidence.",
};

/** Keep dense milestone specifications out of the size-bounded index. */
export function shouldIndexSearchPage(url: string): boolean {
  if (url.includes("/_design")) return false;
  if (!url.startsWith("/roadmap")) return true;
  if (url === "/roadmap" || url === "/roadmap/current-state") return true;
  if (url.includes("/milestones/")) return false;
  return true;
}

function appendText(parts: string[], value: unknown, limit?: number) {
  if (typeof value !== "string") return;
  const text = value.trim();
  if (!text) return;
  parts.push(limit === undefined ? text : text.slice(0, limit));
}

function collectTocTitles(items: SearchTocItem[] | undefined, out: string[]) {
  if (!items) return;
  for (const item of items) {
    appendText(out, item.title);
    collectTocTitles(item.children, out);
  }
}

function collectStructuredContent(
  structured: SearchablePageData["structuredData"],
  parts: string[],
) {
  if (!structured) return;
  for (const heading of structured.headings ?? []) {
    appendText(parts, heading.content);
  }
  for (const block of structured.contents ?? []) {
    appendText(parts, block.heading);
    appendText(parts, block.content, STRUCTURED_CONTENT_CAP);
  }
}

/** Build searchable body text from description, headings, and structured excerpts. */
export function buildSearchContent(page: SearchablePage): string {
  const compactSummary = COMPACT_SEARCH_SUMMARIES[page.url];
  if (compactSummary) return compactSummary;

  const parts: string[] = [];
  appendText(parts, page.data.description ?? page.data.excerpt ?? "");
  collectTocTitles(page.data.toc, parts);
  collectStructuredContent(page.data.structuredData, parts);
  return parts.join("\n");
}
