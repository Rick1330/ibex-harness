/**
 * Attach ibexharness.com (apex) to Cloudflare Pages and document legacy subdomain cutover.
 *
 * Prerequisites: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID
 *
 * After running:
 * 1. Add a Cloudflare Redirect Rule: docs.ibexharness.com/* → https://ibexharness.com/$1 (301)
 * 2. Verify: curl -fsSI https://ibexharness.com/ && bash .github/scripts/docs-smoke.sh https://ibexharness.com
 */
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const PAGES_PROJECT = "ibex-harness-docs";
const PAGES_CNAME_TARGET = `${PAGES_PROJECT}.pages.dev`;
const APEX_HOST = "ibexharness.com";
const LEGACY_DOCS_HOST = "docs.ibexharness.com";
const API_BASE = "https://api.cloudflare.com/client/v4";
const CF_API_ORIGIN = "https://api.cloudflare.com";
const CLOUDFLARE_OPAQUE_ID_RE = /^[0-9a-f]{16,64}$/i;
const ACCOUNTS_RESOURCE_RE =
  /^\/(?:workers\/domains(?:\/[0-9a-f]{16,64})?|pages\/projects\/ibex-harness-docs\/domains)$/;
const ZONES_RESOURCE_RE =
  /^\/[0-9a-f]{16,64}\/dns_records(?:\/[0-9a-f]{16,64})?$/;

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
    name: APEX_HOST,
    "account.id": accountId,
  });
  return `${API_BASE}/zones?${params.toString()}`;
}

async function cloudflareRequest(url, init = {}) {
  const parsed = new URL(url);
  if (parsed.origin !== CF_API_ORIGIN || !parsed.pathname.startsWith("/client/v4/")) {
    throw new Error("Cloudflare API URL not allowlisted");
  }
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

async function listPagesDomains() {
  const result = await cloudflareRequest(
    accountUrl(`/pages/projects/${PAGES_PROJECT}/domains`),
  );
  return Array.isArray(result) ? result : [];
}

async function resolveZoneId() {
  const zones = await cloudflareRequest(buildZonesLookupUrl());
  const zone = Array.isArray(zones) ? zones[0] : undefined;
  if (!zone?.id) {
    throw new Error(`could not resolve Cloudflare zone for ${APEX_HOST}`);
  }
  return assertCloudflareId(zone.id, "zone id");
}

async function attachPagesDomain(hostname) {
  const domains = await listPagesDomains();
  if (domains.some((entry) => entry.name === hostname)) {
    console.log(`[apex-cutover] Pages domain already attached: ${hostname}`);
    return;
  }
  await cloudflareRequest(accountUrl(`/pages/projects/${PAGES_PROJECT}/domains`), {
    method: "POST",
    body: JSON.stringify({ name: hostname }),
  });
  console.log(`[apex-cutover] attached ${hostname} to Pages project ${PAGES_PROJECT}`);
}

async function ensureCname(hostname, zoneId, target) {
  const records = await cloudflareRequest(
    buildZonesApiUrl(
      zoneId,
      `/${zoneId}/dns_records`,
      `?name=${encodeURIComponent(hostname)}`,
    ),
  );
  const existing = Array.isArray(records) ? records : [];
  const cname = existing.find((record) => record.type === "CNAME");

  if (cname?.content === target && cname.proxied === true) {
    console.log(`[apex-cutover] DNS CNAME already points ${hostname} -> ${target}`);
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
          content: target,
          proxied: true,
        }),
      },
    );
    console.log(`[apex-cutover] updated DNS CNAME for ${hostname}`);
    return;
  }

  await cloudflareRequest(buildZonesApiUrl(zoneId, `/${zoneId}/dns_records`), {
    method: "POST",
    body: JSON.stringify({
      type: "CNAME",
      name: hostname,
      content: target,
      proxied: true,
    }),
  });
  console.log(`[apex-cutover] created DNS CNAME for ${hostname}`);
}

async function main() {
  console.log(`[apex-cutover] attaching ${APEX_HOST} to Cloudflare Pages`);
  const zoneId = await resolveZoneId();
  await attachPagesDomain(APEX_HOST);
  await ensureCname(APEX_HOST, zoneId, PAGES_CNAME_TARGET);
  await attachPagesDomain(LEGACY_DOCS_HOST);
  console.log(
    `[apex-cutover] complete — add Redirect Rule: ${LEGACY_DOCS_HOST}/* → https://${APEX_HOST}/$1 (301)`,
  );
}

try {
  await main();
} catch (err) {
  const message = err instanceof Error ? err.message : String(err);
  console.error(`[apex-cutover] failed: ${message}`);
  process.exit(1);
}
