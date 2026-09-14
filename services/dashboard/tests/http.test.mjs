import assert from "node:assert/strict";
import http from "node:http";
import { describe, it } from "node:test";

import { CREDENTIALED_REDIRECT, withCredentialedPolicy } from "../public/http.mjs";

describe("withCredentialedPolicy", () => {
  it("forces include credentials and redirect:error (policy wins)", () => {
    const opts = withCredentialedPolicy({
      method: "POST",
      redirect: "follow",
      credentials: "omit",
      body: '{"pat":"x"}',
    });
    assert.equal(opts.credentials, "include");
    assert.equal(opts.redirect, CREDENTIALED_REDIRECT);
    assert.equal(opts.redirect, "error");
    assert.equal(opts.method, "POST");
  });
});

describe("credentialed fetch redirect policy", () => {
  async function withRedirectPair(status, run) {
    let stealHits = 0;
    const steal = http.createServer((_req, res) => {
      stealHits += 1;
      res.writeHead(200, { "Content-Type": "text/plain" });
      res.end("stolen");
    });
    await new Promise((resolve) => steal.listen(0, "127.0.0.1", resolve));
    const stealPort = /** @type {import("node:net").AddressInfo} */ (steal.address()).port;

    const origin = http.createServer((_req, res) => {
      res.writeHead(status, {
        Location: `http://127.0.0.1:${stealPort}/steal`,
      });
      res.end();
    });
    await new Promise((resolve) => origin.listen(0, "127.0.0.1", resolve));
    const originPort = /** @type {import("node:net").AddressInfo} */ (origin.address()).port;

    try {
      await run(`http://127.0.0.1:${originPort}/login`, () => stealHits);
    } finally {
      await new Promise((resolve) => origin.close(resolve));
      await new Promise((resolve) => steal.close(resolve));
    }
  }

  for (const status of [307, 308]) {
    it(`does not forward credentialed POST to ${status} Location`, async () => {
      await withRedirectPair(status, async (url, stealCount) => {
        await assert.rejects(
          () =>
            fetch(
              url,
              withCredentialedPolicy({
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ pat: "ibex_pat_secret" }),
              }),
            ),
          (err) => {
            assert.ok(err instanceof TypeError || err instanceof Error);
            return true;
          },
        );
        assert.equal(stealCount(), 0, "redirect target must not receive the request");
      });
    });
  }
});
