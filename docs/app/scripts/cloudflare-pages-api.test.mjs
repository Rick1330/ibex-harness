import { describe, expect, it } from "vitest";

import {
  assertCloudflareId,
  buildAccountsApiUrl,
  buildZonesApiUrl,
  buildZonesLookupUrl,
} from "./lib/cloudflare-pages-api.mjs";

describe("cloudflare-pages-api", () => {
  it("validates opaque Cloudflare ids", () => {
    expect(assertCloudflareId("0123456789abcdef", "test")).toBe(
      "0123456789abcdef",
    );
    expect(() => assertCloudflareId("bad", "test")).toThrow(
      "unexpected test from Cloudflare API",
    );
  });

  it("builds allowlisted accounts API URLs", () => {
    const url = buildAccountsApiUrl(
      "0123456789abcdef",
      "/pages/projects/ibex-harness-docs/domains",
    );
    expect(url).toBe(
      "https://api.cloudflare.com/client/v4/accounts/0123456789abcdef/pages/projects/ibex-harness-docs/domains",
    );
    expect(() =>
      buildAccountsApiUrl("0123456789abcdef", "/pages/projects/other/domains"),
    ).toThrow("disallowed Cloudflare accounts API path");
  });

  it("builds allowlisted zones API URLs", () => {
    const url = buildZonesApiUrl(
      "0123456789abcdef",
      "/0123456789abcdef/dns_records",
      "?name=ibexharness.com",
    );
    expect(url).toContain("/zones/0123456789abcdef/dns_records");
    expect(url).toContain("name=ibexharness.com");
  });

  it("builds zone lookup URL with account filter", () => {
    process.env.CLOUDFLARE_ACCOUNT_ID = "0123456789abcdef";
    const url = buildZonesLookupUrl("ibexharness.com");
    expect(url).toContain("name=ibexharness.com");
    expect(url).toContain("account.id=0123456789abcdef");
    delete process.env.CLOUDFLARE_ACCOUNT_ID;
  });
});
