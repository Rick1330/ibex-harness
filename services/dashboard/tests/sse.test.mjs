import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  isAllowedApiHost,
  isLoopbackHost,
  pickApiBase,
  resolveApiBase,
} from "../public/api_base.mjs";
import { buildLoginBody, parseSSEBlock, shouldAcceptEventId } from "../public/sse.mjs";
import {
  classifyStreamStatus,
  isAuthFailure,
  isPermanentClientError,
  reconnectDelayMs,
} from "../public/stream.mjs";

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

describe("classifyStreamStatus", () => {
  function fakeResp(status, headers = {}) {
    return {
      status,
      ok: status >= 200 && status < 300,
      body: {},
      headers: { get: (k) => headers[k] ?? null },
    };
  }

  it("classifies drain, auth, retry, and permanent 4xx", () => {
    assert.equal(classifyStreamStatus(fakeResp(503, { "X-IBEX-Drain": "1" })), "drained");
    assert.equal(classifyStreamStatus(fakeResp(401)), "auth");
    assert.equal(classifyStreamStatus(fakeResp(429)), "retry");
    assert.equal(classifyStreamStatus(fakeResp(404)), "stop");
    assert.equal(classifyStreamStatus(fakeResp(200)), "ok");
    assert.equal(isAuthFailure(403), true);
    assert.equal(isPermanentClientError(400), true);
  });
});

describe("reconnectDelayMs", () => {
  it("honors Retry-After and caps exponential backoff", () => {
    assert.equal(reconnectDelayMs(0, "5"), 5000);
    const delay = reconnectDelayMs(0, null);
    assert.ok(delay >= 1000 && delay < 1250);
    assert.ok(reconnectDelayMs(20, null) <= 30_250);
  });
});
