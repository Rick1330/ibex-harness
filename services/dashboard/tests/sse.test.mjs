import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  buildLoginBody,
  isAllowedApiHost,
  isLoopbackHost,
  parseSSEBlock,
  pickApiBase,
  resolveApiBase,
  shouldAcceptEventId,
} from "../public/sse.mjs";

describe("buildLoginBody", () => {
  it("trims PAT and JSON-encodes", () => {
    assert.equal(buildLoginBody("  ibex_pat_x  "), JSON.stringify({ pat: "ibex_pat_x" }));
  });
});

describe("parseSSEBlock", () => {
  it("parses id and data", () => {
    const parsed = parseSSEBlock('id: 3\nevent: operator.evidence\ndata:{"n":3}');
    assert.equal(parsed.id, 3);
    assert.equal(parsed.data, '{"n":3}');
  });

  it("ignores heartbeats", () => {
    assert.equal(parseSSEBlock(": heartbeat"), null);
  });
});

describe("shouldAcceptEventId", () => {
  it("rejects duplicates and older ids", () => {
    assert.equal(shouldAcceptEventId(2, 2), false);
    assert.equal(shouldAcceptEventId(2, 1), false);
    assert.equal(shouldAcceptEventId(2, 3), true);
    assert.equal(shouldAcceptEventId(null, 1), true);
  });
});

describe("resolveApiBase", () => {
  it("allows loopback HTTP and product HTTPS", () => {
    assert.equal(resolveApiBase("http://localhost:8010/"), "http://localhost:8010");
    assert.equal(resolveApiBase("https://api.ibexharness.com"), "https://api.ibexharness.com");
    assert.equal(isAllowedApiHost("operator.ibexharness.com"), true);
    assert.equal(isLoopbackHost("127.0.0.1"), true);
  });

  it("rejects non-http schemes, foreign hosts, and non-loopback HTTP", () => {
    assert.equal(resolveApiBase("javascript:alert(1)"), null);
    assert.equal(resolveApiBase("http://evil.example"), null);
    assert.equal(resolveApiBase("http://api.ibexharness.com"), null);
    assert.equal(resolveApiBase("http://user:pass@localhost:8010"), null);
  });

  it("pickApiBase falls back to localhost default", () => {
    assert.equal(pickApiBase(""), "http://localhost:8010");
    assert.equal(pickApiBase("https://api.ibexharness.com"), "https://api.ibexharness.com");
  });
});
