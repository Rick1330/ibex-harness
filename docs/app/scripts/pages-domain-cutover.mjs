import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import {
  accountUrl,
  assertCloudflareId,
  attachPagesDomain,
  cloudflareRequest,
  ensureCname,
  listPagesDomains,
  PAGES_CNAME_TARGET,
  resolveZoneId,
} from "./lib/cloudflare-pages-api.mjs";

const PRODUCTION_HOST = "docs.ibexharness.com";
const LEGACY_WORKER = "ibex-harness-docs";
const ZONE_APEX = "ibexharness.com";
const WORKER_ALREADY_MISSING_RE =
  /not found|does not exist|no such script|10007|couldn't find/i;

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(scriptDir, "..");

const require = createRequire(import.meta.url);
const wranglerBin = path.join(
  path.dirname(require.resolve("wrangler/package.json")),
  "bin/wrangler.js",
);

function assertHostname(value, expected) {
  if (value !== expected) {
    throw new Error("unexpected hostname from Cloudflare API");
  }
  return value;
}

async function listWorkerDomains() {
  const result = await cloudflareRequest(accountUrl("/workers/domains"));
  return Array.isArray(result) ? result : [];
}

async function resolveHostZoneId(hostname) {
  const pagesDomains = await listPagesDomains();
  const pagesMatch = pagesDomains.find((entry) => entry.name === hostname);
  if (pagesMatch?.zone_tag) {
    return assertCloudflareId(pagesMatch.zone_tag, "zone id");
  }
  return resolveZoneId(ZONE_APEX);
}

async function removeWorkerDomain(hostname) {
  const domains = await listWorkerDomains();
  const match = domains.find((entry) => entry.hostname === hostname);
  if (!match) {
    console.log(`[cutover] no Worker custom domain for ${hostname}`);
    return null;
  }
  assertHostname(match.hostname, PRODUCTION_HOST);
  const domainId = assertCloudflareId(match.id, "worker domain id");
  const zoneId = match.zone_id
    ? assertCloudflareId(match.zone_id, "zone id")
    : null;
  await cloudflareRequest(accountUrl(`/workers/domains/${domainId}`), {
    method: "DELETE",
  });
  console.log(`[cutover] removed Worker custom domain ${hostname}`);
  return zoneId;
}

function runWranglerDeleteWorker() {
  return new Promise((resolve, reject) => {
    let stderr = "";
    const child = spawn(
      process.execPath,
      [wranglerBin, "delete", LEGACY_WORKER, "--force"],
      {
        cwd: appRoot,
        env: process.env,
        stdio: ["ignore", "inherit", "pipe"],
        shell: false,
      },
    );
    child.stderr?.on("data", (chunk) => {
      const text = chunk.toString();
      stderr += text;
      process.stderr.write(chunk);
    });
    child.once("error", reject);
    child.once("exit", (code) => {
      if (code === 0) {
        console.log(`[cutover] deleted legacy Worker ${LEGACY_WORKER}`);
        resolve(undefined);
        return;
      }
      if (WORKER_ALREADY_MISSING_RE.test(stderr)) {
        console.log(`[cutover] legacy Worker ${LEGACY_WORKER} already removed`);
        resolve(undefined);
        return;
      }
      reject(
        new Error(`wrangler delete ${LEGACY_WORKER} exited ${code ?? "unknown"}`),
      );
    });
  });
}

async function main() {
  console.log(`[cutover] moving ${PRODUCTION_HOST} from Worker to Pages`);
  let zoneId = await removeWorkerDomain(PRODUCTION_HOST);
  await attachPagesDomain(PRODUCTION_HOST, "[cutover]");
  if (!zoneId) {
    zoneId = await resolveHostZoneId(PRODUCTION_HOST);
  }
  await ensureCname(PRODUCTION_HOST, zoneId, PAGES_CNAME_TARGET, "[cutover]");
  await runWranglerDeleteWorker();
  console.log("[cutover] complete — verify with docs-smoke.sh on production URL");
}

try {
  await main();
} catch (err) {
  const message = err instanceof Error ? err.message : String(err);
  console.error(`[cutover] failed: ${message}`);
  console.error(
    "[cutover] check Cloudflare dashboard for domain and Worker state",
  );
  process.exit(1);
}
