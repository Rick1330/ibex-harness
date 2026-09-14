import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  buildLoginBody,
  parseSSEBlock,
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
