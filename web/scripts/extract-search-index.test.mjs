import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { assertSearchIndexContract } from "./extract-search-index.mjs";

const requiredDocs = [
  {
    url: "/docs/adr/0081-fail-closed-proxy-runtime-controls",
    token: "SERVICE_DEGRADED",
  },
  { url: "/roadmap/phase-4-multi-provider/findings", token: "F4-037" },
  { url: "/roadmap/phase-4-multi-provider/risks", token: "Redis" },
];
const excludedMilestone =
  "/roadmap/phase-4-multi-provider/milestones/4.p.0-runtime-topology-environment-contract";

const routeArtifact = (root, url) =>
  path.join(root, ".next", "server", "app", `${url.slice(1)}.html`);

function makeBody(docs = requiredDocs.map(({ url, token }) => ({ url, content: token }))) {
  return JSON.stringify({ docs: { docs } });
}

describe("assertSearchIndexContract", () => {
  let routeRoot;

  afterEach(async () => {
    if (routeRoot) await rm(routeRoot, { recursive: true, force: true });
  });

  async function prepareRoutes(docs = requiredDocs) {
    routeRoot = await mkdtemp(path.join(os.tmpdir(), "ibex-search-contract-"));
    await Promise.all(
      docs.map(async ({ url }) => {
        const target = routeArtifact(routeRoot, url);
        await mkdir(path.dirname(target), { recursive: true });
        await writeFile(target, "<html></html>");
      }),
    );
  }

  it("accepts a valid export", async () => {
    await prepareRoutes();
    await expect(
      assertSearchIndexContract(makeBody(), { routeRoot }),
    ).resolves.toBeUndefined();
  });

  it("rejects a missing required document", async () => {
    const docs = requiredDocs.slice(1).map(({ url, token }) => ({ url, content: token }));
    await prepareRoutes(docs);
    await expect(
      assertSearchIndexContract(makeBody(docs), { routeRoot }),
    ).rejects.toThrow("required search document is missing");
  });

  it("rejects a missing required token", async () => {
    await prepareRoutes();
    const docs = requiredDocs.map(({ url }) => ({ url, content: "other" }));
    await expect(
      assertSearchIndexContract(makeBody(docs), { routeRoot }),
    ).rejects.toThrow("missing its required token");
  });

  it("rejects a missing compiled route artifact", async () => {
    await prepareRoutes(requiredDocs.slice(0, 2));
    await expect(
      assertSearchIndexContract(makeBody(), { routeRoot }),
    ).rejects.toThrow("has no compiled route artifact");
  });

  it("rejects an included dense milestone", async () => {
    const docs = [
      ...requiredDocs.map(({ url, token }) => ({ url, content: token })),
      { url: excludedMilestone, content: "dense milestone" },
    ];
    await prepareRoutes();
    await expect(
      assertSearchIndexContract(makeBody(docs), { routeRoot }),
    ).rejects.toThrow("dense milestone unexpectedly included");
  });
});
