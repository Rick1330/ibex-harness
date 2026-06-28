import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const PAGES_PROJECT = "ibex-harness-docs";
const PAGES_CNAME_TARGET = `${PAGES_PROJECT}.pages.dev`;
const PRODUCTION_HOST = "docs.ibexharness.com";
const LEGACY_WORKER = "ibex-harness-docs";
const API_BASE = "https://api.cloudflare.com/client/v4";
const CF_API_ORIGIN = "https://api.cloudflare.com";
const ZONE_APEX = "ibexharness.com";
const CLOUDFLARE_OPAQUE_ID_RE = /^[0-9a-f]{16,64}$/i;
const ACCOUNTS_RESOURCE_RE =
  /^\/(?:workers\/domains(?:\/[0-9a-f]{16,64})?|pages\/projects\/ibex-harness-docs\/domains)$/;
const ZONES_RESOURCE_RE =
  /^\/[0-9a-f]{16,64}\/dns_records(?:\/[0-9a-f]{16,64})?$/;
const WORKER_ALREADY_MISSING_RE =
  /not found|does not exist|no such script|10007|couldn't find/i;

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
  if (typeof value !== "string" || !CLOUDFLARE_OPAQUE_ID_RE.test(value)) {
    throw new Error(`unexpected ${label} from Cloudflare API`);
  }
  return value;
}

function assertHostname(value, expected) {
  if (value !== expected) {
    throw new Error("unexpected hostname from Cloudflare API");
  }
  return value;
}

function buildAccountsApiUrl(accountId, resourcePath) {
  assertCloudflareId(accountId, "account id");
  if (!ACCOUNTS_RESOURCE_RE.test(resourcePath)) {
    throw new Error("disallowed Cloudflare accounts API path");
  }
  return `${API_BASE}/accounts/${accountId}${resourcePath}`;
}

function buildZonesApiUrl(zoneId, resourcePath, query = "") {
  assertCloudflareId(zoneId, "zone id");
  if (!ZONES_RESOURCE_RE.test(resourcePath)) {
    throw new Error("disallowed Cloudflare zones API path");
  }
  return `${API_BASE}/zones${resourcePath}${query}`;
}

function buildZonesLookupUrl() {
  const accountId = requireEnv("CLOUDFLARE_ACCOUNT_ID");
  assertCloudflareId(accountId, "account id");
  const params = new URLSearchParams({
    name: ZONE_APEX,
    "account.id": accountId,
  });
  return `${API_BASE}/zones?${params.toString()}`;
}

function assertFetchTarget(url) {
  const parsed = new URL(url);
  if (parsed.origin !== CF_API_ORIGIN || !parsed.pathname.startsWith("/client/v4/")) {
    throw new Error("Cloudflare API URL not allowlisted");
  }
}

async function cloudflareRequest(url, init = {}) {
  assertFetchTarget(url);
  const token = requireEnv("CLOUDFLARE_API_TOKEN");
  const response = await fetch(url, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...init.headers,
    },
  });
  const text = await response.text();
  let body = { success: response.ok };
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { success: false, errors: [{ message: text }] };
    }
  }
  if (!response.ok || body.success === false) {
    const detail = Array.isArray(body.errors)
      ? body.errors.map((e) => e.message ?? JSON.stringify(e)).join("; ")
      : response.statusText;
    throw new Error(
      `Cloudflare API ${url} failed (${response.status}): ${detail}`,
    );
  }
  return body.result;
}

function accountUrl(suffix) {
  const accountId = requireEnv("CLOUDFLARE_ACCOUNT_ID");
  return buildAccountsApiUrl(accountId, suffix);
}

async function listWorkerDomains() {
  const result = await cloudflareRequest(accountUrl("/workers/domains"));
  return Array.isArray(result) ? result : [];
}

async function resolveZoneId(hostname) {
  if (hostname !== PRODUCTION_HOST) {
    throw new Error("unexpected hostname for zone resolution");
  }

  const pagesDomains = await listPagesDomains();
  const pagesMatch = pagesDomains.find((entry) => entry.name === hostname);
  if (pagesMatch?.zone_tag) {
    return assertCloudflareId(pagesMatch.zone_tag, "zone id");
  }

  const zones = await cloudflareRequest(buildZonesLookupUrl());
  const zone = Array.isArray(zones) ? zones[0] : undefined;
  if (!zone?.id) {
    throw new Error(`could not resolve Cloudflare zone for ${hostname}`);
  }
  return assertCloudflareId(zone.id, "zone id");
}

async function ensurePagesDnsCname(hostname, zoneId) {
  if (hostname !== PRODUCTION_HOST) {
    throw new Error("unexpected hostname for DNS CNAME");
  }

  const records = await cloudflareRequest(
    buildZonesApiUrl(
      zoneId,
      `/${zoneId}/dns_records`,
      `?name=${encodeURIComponent(hostname)}`,
    ),
  );
  const existing = Array.isArray(records) ? records : [];
  const cname = existing.find((record) => record.type === "CNAME");

  if (cname?.content === PAGES_CNAME_TARGET && cname.proxied === true) {
    console.log(`[cutover] DNS CNAME already points to ${PAGES_CNAME_TARGET}`);
    return;
  }

  if (cname) {
    const cnameId = assertCloudflareId(cname.id, "dns record id");
    await cloudflareRequest(
      buildZonesApiUrl(zoneId, `/${zoneId}/dns_records/${cnameId}`),
      {
        method: "PATCH",
        body: JSON.stringify({
          type: "CNAME",
          content: PAGES_CNAME_TARGET,
          proxied: true,
        }),
      },
    );
    console.log(
      `[cutover] updated DNS CNAME for ${hostname} -> ${PAGES_CNAME_TARGET}`,
    );
    return;
  }

  await cloudflareRequest(buildZonesApiUrl(zoneId, `/${zoneId}/dns_records`), {
    method: "POST",
    body: JSON.stringify({
      type: "CNAME",
      name: hostname,
      content: PAGES_CNAME_TARGET,
      proxied: true,
    }),
  });
  console.log(
    `[cutover] created DNS CNAME for ${hostname} -> ${PAGES_CNAME_TARGET}`,
  );
}

async function removeWorkerDomain(hostname) {
  if (hostname !== PRODUCTION_HOST) {
    throw new Error("unexpected hostname for Worker domain removal");
  }

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

async function listPagesDomains() {
  const result = await cloudflareRequest(
    accountUrl(`/pages/projects/${PAGES_PROJECT}/domains`),
  );
  return Array.isArray(result) ? result : [];
}

async function attachPagesDomain(hostname) {
  if (hostname !== PRODUCTION_HOST) {
    throw new Error("unexpected hostname for Pages domain attach");
  }

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
  await attachPagesDomain(PRODUCTION_HOST);
  if (!zoneId) {
    zoneId = await resolveZoneId(PRODUCTION_HOST);
  }
  await ensurePagesDnsCname(PRODUCTION_HOST, zoneId);
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
