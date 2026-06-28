import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const PAGES_PROJECT = "ibex-harness-docs";
const PRODUCTION_HOST = "docs.ibexharness.com";
const LEGACY_WORKER = "ibex-harness-docs";
const API_BASE = "https://api.cloudflare.com/client/v4";
const CLOUDFLARE_ID_RE = /^[0-9a-f]{32}$/i;

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(scriptDir, "..");

const require = createRequire(import.meta.url);
const wranglerBin = path.join(
  path.dirname(require.resolve("wrangler/package.json")),
  "bin/wrangler.js",
);

function requireEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}

function assertCloudflareId(value, label) {
  if (typeof value !== "string" || !CLOUDFLARE_ID_RE.test(value)) {
    throw new Error(`unexpected ${label} from Cloudflare API`);
  }
  return value;
}

function assertHostname(value, expected) {
  if (value !== expected) {
    throw new Error(`unexpected hostname from Cloudflare API`);
  }
  return value;
}

async function cloudflareRequest(url, init = {}) {
  const token = requireEnv("CLOUDFLARE_API_TOKEN");
  const response = await fetch(url, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...init.headers,
    },
  });
  const body = await response.json();
  if (!response.ok || body.success === false) {
    throw new Error(`Cloudflare API request failed with status ${response.status}`);
  }
  return body.result;
}

function accountUrl(suffix) {
  const accountId = requireEnv("CLOUDFLARE_ACCOUNT_ID");
  assertCloudflareId(accountId, "account id");
  return `${API_BASE}/accounts/${accountId}${suffix}`;
}

async function listWorkerDomains() {
  try {
    return await cloudflareRequest(accountUrl("/workers/domains"));
  } catch {
    return [];
  }
}

async function removeWorkerDomain(hostname) {
  const domains = await listWorkerDomains();
  const match = domains.find((entry) => entry.hostname === hostname);
  if (!match) {
    console.log(`[cutover] no Worker custom domain for ${hostname}`);
    return;
  }
  assertHostname(match.hostname, PRODUCTION_HOST);
  const domainId = assertCloudflareId(match.id, "worker domain id");
  await cloudflareRequest(accountUrl(`/workers/domains/${domainId}`), {
    method: "DELETE",
  });
  console.log(`[cutover] removed Worker custom domain ${hostname}`);
}

async function listPagesDomains() {
  try {
    return await cloudflareRequest(
      accountUrl(`/pages/projects/${PAGES_PROJECT}/domains`),
    );
  } catch {
    return [];
  }
}

async function attachPagesDomain(hostname) {
  const domains = await listPagesDomains();
  if (domains.some((entry) => entry.name === hostname)) {
    console.log(`[cutover] Pages domain already attached: ${hostname}`);
    return;
  }
  await cloudflareRequest(accountUrl(`/pages/projects/${PAGES_PROJECT}/domains`), {
    method: "POST",
    body: JSON.stringify({ name: hostname }),
  });
  console.log(`[cutover] attached ${hostname} to Pages project ${PAGES_PROJECT}`);
}

function runWranglerDeleteWorker() {
  return new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [wranglerBin, "delete", LEGACY_WORKER, "--force"],
      {
        cwd: appRoot,
        env: process.env,
        stdio: "inherit",
        shell: false,
      },
    );
    child.once("error", reject);
    child.once("exit", (code) => {
      if (code === 0) {
        console.log(`[cutover] deleted legacy Worker ${LEGACY_WORKER}`);
        resolve(undefined);
        return;
      }
      console.warn(
        `[cutover] wrangler delete ${LEGACY_WORKER} exited ${code ?? "unknown"} (may already be removed)`,
      );
      resolve(undefined);
    });
  });
}

async function main() {
  console.log(`[cutover] moving ${PRODUCTION_HOST} from Worker to Pages`);
  await removeWorkerDomain(PRODUCTION_HOST);
  await runWranglerDeleteWorker();
  await attachPagesDomain(PRODUCTION_HOST);
  console.log("[cutover] complete — verify with docs-smoke.sh on production URL");
}

try {
  await main();
} catch {
  console.error("[cutover] failed — see Cloudflare dashboard for domain and Worker state");
  process.exit(1);
}
