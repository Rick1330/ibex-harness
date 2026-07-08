import { describe, expect, it } from "vitest";

import { mapSimpleSearchHits } from "@/hooks/use-static-docs-search";

describe("mapSimpleSearchHits", () => {
  it("maps Orama hits to fumadocs page results", () => {
    const hits = [
      {
        document: {
          title: "Rate limiting",
          url: "/docs/proxy/rate-limiting",
        },
      },
    ];

    expect(mapSimpleSearchHits(hits)).toEqual([
      {
        type: "page",
        content: "Rate limiting",
        id: "/docs/proxy/rate-limiting",
        url: "/docs/proxy/rate-limiting",
      },
    ]);
  });
});
