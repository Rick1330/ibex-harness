export const PAGES_PROJECT = "ibex-harness-docs";
export const PAGES_CNAME_TARGET = `${PAGES_PROJECT}.pages.dev`;

const API_BASE = "https://api.cloudflare.com/client/v4";
const CF_API_ORIGIN = "https://api.cloudflare.com";
const CLOUDFLARE_OPAQUE_ID_RE = /^[0-9a-f]{16,64}$/i;
const ALLOWED_HOSTNAMES = new Set([
  "ibexharness.com",
  "docs.ibexharness.com",
]);
const ALLOWED_ZONE_NAMES = new Set(["ibexharness.com"]);
const ACCOUNTS_RESOURCE_RE =
  /^\/(?:workers\/domains(?:\/[0-9a-f]{16,64})?|pages\/projects\/ibex-harness-docs\/domains(?:\/[a-z0-9.-]+)?)$/;
const ZONES_RESOURCE_RE =
  /^\/[0-9a-f]{16,64}\/dns_records(?:\/[0-9a-f]{16,64})?$/;

export function requireEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}

export function assertAllowedHostname(hostname) {
  if (!ALLOWED_HOSTNAMES.has(hostname)) {
    throw new Error("disallowed hostname for Cloudflare Pages operation");
  }
  return hostname;
}

export function assertAllowedZoneName(zoneName) {
  if (!ALLOWED_ZONE_NAMES.has(zoneName)) {
    throw new Error("disallowed zone name for Cloudflare DNS operation");
  }
  return zoneName;
}

export function assertCloudflareId(value, label) {
  if (typeof value !== "string" || !CLOUDFLARE_OPAQUE_ID_RE.test(value)) {
    throw new Error(`unexpected ${label} from Cloudflare API`);
  }
  return value;
}

export function buildAccountsApiUrl(accountId, resourcePath) {
  assertCloudflareId(accountId, "account id");
  if (!ACCOUNTS_RESOURCE_RE.test(resourcePath)) {
    throw new Error("disallowed Cloudflare accounts API path");
  }
  return `${API_BASE}/accounts/${accountId}${resourcePath}`;
}

export function buildZonesApiUrl(zoneId, resourcePath, query = "") {
  assertCloudflareId(zoneId, "zone id");
  if (!ZONES_RESOURCE_RE.test(resourcePath)) {
    throw new Error("disallowed Cloudflare zones API path");
  }
  return `${API_BASE}/zones${resourcePath}${query}`;
}

export function buildZonesLookupUrl(zoneName) {
  assertAllowedZoneName(zoneName);
  const accountId = requireEnv("CLOUDFLARE_ACCOUNT_ID");
  assertCloudflareId(accountId, "account id");
  const params = new URLSearchParams({
    name: zoneName,
    "account.id": accountId,
  });
  return `${API_BASE}/zones?${params.toString()}`;
}

export function assertFetchTarget(url) {
  const parsed = new URL(url);
  if (parsed.origin !== CF_API_ORIGIN || !parsed.pathname.startsWith("/client/v4/")) {
    throw new Error("Cloudflare API URL not allowlisted");
  }
}

async function cloudflareFetch(validatedUrl, init = {}) {
  assertFetchTarget(validatedUrl);
  const token = requireEnv("CLOUDFLARE_API_TOKEN");
  const response = await fetch(validatedUrl, {
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
      body = { success: false };
    }
  }
  if (!response.ok || body.success === false) {
    throw new Error(`Cloudflare API request failed (${response.status})`);
  }
  return body.result;
}

async function cloudflareAccountsRequest(resourcePath, init = {}) {
  return cloudflareFetch(accountUrl(resourcePath), init);
}

async function cloudflareZonesRequest(zoneId, resourcePath, query = "", init = {}) {
  return cloudflareFetch(buildZonesApiUrl(zoneId, resourcePath, query), init);
}

export async function cloudflareRequest(url, init = {}) {
  return cloudflareFetch(url, init);
}

export function accountUrl(suffix) {
  const accountId = requireEnv("CLOUDFLARE_ACCOUNT_ID");
  return buildAccountsApiUrl(accountId, suffix);
}

export async function listPagesDomains() {
  const result = await cloudflareAccountsRequest(
    `/pages/projects/${PAGES_PROJECT}/domains`,
  );
  return Array.isArray(result) ? result : [];
}

export async function attachPagesDomain(hostname, logPrefix = "[cf]") {
  assertAllowedHostname(hostname);
  const domains = await listPagesDomains();
  if (domains.some((entry) => entry.name === hostname)) {
    console.log(`${logPrefix} Pages domain already attached`);
    return;
  }
  await cloudflareAccountsRequest(`/pages/projects/${PAGES_PROJECT}/domains`, {
    method: "POST",
    body: JSON.stringify({ name: hostname }),
  });
  console.log(`${logPrefix} attached hostname to Pages project ${PAGES_PROJECT}`);
}

export async function detachPagesDomain(hostname, logPrefix = "[cf]") {
  assertAllowedHostname(hostname);
  const domains = await listPagesDomains();
  const match = domains.some((entry) => entry.name === hostname);
  if (!match) {
    console.log(`${logPrefix} Pages domain not attached`);
    return;
  }
  await cloudflareAccountsRequest(
    `/pages/projects/${PAGES_PROJECT}/domains/${hostname}`,
    { method: "DELETE" },
  );
  console.log(`${logPrefix} detached hostname from Pages project`);
}

export async function resolveZoneId(zoneName) {
  assertAllowedZoneName(zoneName);
  const zones = await cloudflareFetch(buildZonesLookupUrl(zoneName));
  const zone = Array.isArray(zones) ? zones[0] : undefined;
  if (!zone?.id) {
    throw new Error("could not resolve Cloudflare zone");
  }
  return assertCloudflareId(zone.id, "zone id");
}

async function listDnsRecords(hostname, zoneId) {
  assertAllowedHostname(hostname);
  const records = await cloudflareZonesRequest(
    zoneId,
    `/${zoneId}/dns_records`,
    `?name=${encodeURIComponent(hostname)}`,
  );
  return Array.isArray(records) ? records : [];
}

async function deleteDnsRecord(zoneId, recordId, logPrefix) {
  const id = assertCloudflareId(recordId, "dns record id");
  await cloudflareZonesRequest(zoneId, `/${zoneId}/dns_records/${id}`, "", {
    method: "DELETE",
  });
  console.log(`${logPrefix} deleted DNS record`);
}

export async function removeConflictingDnsRecords(hostname, zoneId, logPrefix) {
  assertAllowedHostname(hostname);
  const existing = await listDnsRecords(hostname, zoneId);
  for (const record of existing) {
    if (record.type === "A" || record.type === "AAAA") {
      await deleteDnsRecord(zoneId, record.id, logPrefix);
    }
  }
}

export async function deleteHostnameDnsRecords(hostname, zoneId, logPrefix) {
  assertAllowedHostname(hostname);
  const existing = await listDnsRecords(hostname, zoneId);
  for (const record of existing) {
    await deleteDnsRecord(zoneId, record.id, logPrefix);
  }
}

export async function ensureCname(hostname, zoneId, target, logPrefix = "[cf]") {
  assertAllowedHostname(hostname);
  if (target !== PAGES_CNAME_TARGET) {
    throw new Error("disallowed CNAME target for Cloudflare DNS operation");
  }
  await removeConflictingDnsRecords(hostname, zoneId, logPrefix);

  const existing = await listDnsRecords(hostname, zoneId);
  const cname = existing.find((record) => record.type === "CNAME");

  if (cname?.content === target && cname.proxied === true) {
    console.log(`${logPrefix} DNS CNAME already configured`);
    return;
  }

  if (cname) {
    const cnameId = assertCloudflareId(cname.id, "dns record id");
    await cloudflareZonesRequest(zoneId, `/${zoneId}/dns_records/${cnameId}`, "", {
      method: "PATCH",
      body: JSON.stringify({
        type: "CNAME",
        content: target,
        proxied: true,
      }),
    });
    console.log(`${logPrefix} updated DNS CNAME`);
    return;
  }

  await cloudflareZonesRequest(zoneId, `/${zoneId}/dns_records`, "", {
    method: "POST",
    body: JSON.stringify({
      type: "CNAME",
      name: hostname,
      content: target,
      proxied: true,
    }),
  });
  console.log(`${logPrefix} created DNS CNAME`);
}
