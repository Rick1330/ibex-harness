/** Canonical URL for the unified IBEX Harness site (landing + docs). */
export const SITE_URL = "https://ibexharness.com";

/** @deprecated Use {@link SITE_URL}. Alias kept for existing imports. */
export const DOCS_SITE_URL = SITE_URL;

/** @deprecated Use {@link SITE_URL}. Alias kept for existing imports. */
export const MARKETING_SITE_URL = SITE_URL;

/** Legacy subdomain — 301 redirects to {@link SITE_URL} at the edge. */
export const LEGACY_DOCS_HOST = "https://docs.ibexharness.com";

export const SITE_LLMS_URL = `${SITE_URL}/llms.txt`;
export const SITE_AI_URL = `${SITE_URL}/ai.txt`;

/** @deprecated Use {@link SITE_LLMS_URL}. */
export const DOCS_LLMS_URL = SITE_LLMS_URL;

/** @deprecated Use {@link SITE_AI_URL}. */
export const DOCS_AI_URL = SITE_AI_URL;

/** @deprecated Use {@link SITE_LLMS_URL}. */
export const MARKETING_LLMS_URL = SITE_LLMS_URL;

/** @deprecated Use {@link SITE_AI_URL}. */
export const MARKETING_AI_URL = SITE_AI_URL;

export const SITE_DESCRIPTION =
  "Self-hosted LLM proxy with persistent agent memory, context assembly, and behavioral drift detection for AI agents at scale.";

export const SITE_KEYWORDS = [
  "IBEX Harness",
  "LLM proxy",
  "AI agent memory",
  "OpenAI-compatible proxy",
  "multi-tenant AI",
  "agent infrastructure",
  "context assembly",
  "drift detection",
].join(", ");
