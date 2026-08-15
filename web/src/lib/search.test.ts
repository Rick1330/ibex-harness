import { describe, expect, it } from "vitest";

import { buildSearchContent } from "@/lib/search-content";

describe("buildSearchContent", () => {
  it("includes description and toc titles for body keyword discoverability", () => {
    const content = buildSearchContent({
      url: "/docs/proxy/directives",
      data: {
        title: "Directives",
        description: "Org-scoped directives and system-prompt injection.",
        toc: [
          { title: "Injection modes" },
          { title: "Configuration", children: [{ title: "IBEX_DIRECTIVE_CACHE_TTL" }] },
        ],
      },
    });

    expect(content).toContain("Org-scoped directives");
    expect(content).toContain("Injection modes");
    expect(content).toContain("IBEX_DIRECTIVE_CACHE_TTL");
  });

  it("includes structuredData excerpts when present", () => {
    const content = buildSearchContent({
      url: "/docs/proxy/sessions",
      data: {
        description: "Sticky session IDs",
        structuredData: {
          headings: [{ content: "Idle sweeper" }],
          contents: [{ heading: "Checkpoints", content: "Idempotency and async checkpoint writes" }],
        },
      },
    });

    expect(content).toContain("Idle sweeper");
    expect(content).toContain("Checkpoints");
    expect(content).toContain("async checkpoint");
  });
});
