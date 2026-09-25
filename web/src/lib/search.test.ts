import { describe, expect, it } from "vitest";

import { buildSearchContent, shouldIndexSearchPage } from "@/lib/search-content";

describe("shouldIndexSearchPage", () => {
  it("keeps public documentation and roadmap hubs searchable", () => {
    expect(shouldIndexSearchPage("/docs/proxy/rate-limiting")).toBe(true);
    expect(shouldIndexSearchPage("/roadmap/current-state")).toBe(true);
    expect(shouldIndexSearchPage("/roadmap/phase-4-multi-provider")).toBe(true);
  });

  it("keeps compact Phase 4 register summaries searchable and excludes milestone specs", () => {
    expect(shouldIndexSearchPage("/roadmap/phase-4-multi-provider/findings")).toBe(true);
    expect(shouldIndexSearchPage("/roadmap/phase-4-multi-provider/risks")).toBe(true);
    expect(shouldIndexSearchPage("/roadmap/phase-4-multi-provider/milestones/4.p.0-runtime-topology-environment-contract")).toBe(false);
    expect(shouldIndexSearchPage("/docs/adr/0081-fail-closed-proxy-runtime-controls")).toBe(true);
  });
});

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

  it("caps each structured content block at 800 characters", () => {
    const content = buildSearchContent({
      url: "/docs/proxy/sessions",
      data: {
        structuredData: {
          contents: [{ content: "a".repeat(801) }],
        },
      },
    });

    expect(content).toBe("a".repeat(800));
  });

  it("keeps ADR-0081 discoverable without indexing its full dense body", () => {
    const content = buildSearchContent({
      url: "/docs/adr/0081-fail-closed-proxy-runtime-controls",
      data: {
        description: "Redis-backed rate-limit and organization model-policy dependency failure behavior.",
        structuredData: { contents: [{ content: "x".repeat(5000) }] },
      },
    });

    expect(content).toContain("IBEX_ENV");
    expect(content).toContain("Redis");
    expect(content).toContain("SERVICE_DEGRADED");
    expect(content).toContain("organization policy");
    expect(content).toContain("501");
    expect(content.length).toBeLessThan(500);
  });

  it("keeps new Phase 4 P0 findings discoverable through a bounded register summary", () => {
    const content = buildSearchContent({
      url: "/roadmap/phase-4-multi-provider/findings",
      data: { structuredData: { contents: [{ content: "x".repeat(5000) }] } },
    });

    expect(content).toContain("F4-034");
    expect(content).toContain("F4-036");
    expect(content).toContain("F4-037");
    expect(content.length).toBeLessThan(1000);
  });
});
