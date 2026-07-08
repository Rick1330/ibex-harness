export const PAGES_PROJECT = "ibex-harness-docs";
export const PAGES_CNAME_TARGET = `${PAGES_PROJECT}.pages.dev`;

const API_BASE = "https://api.cloudflare.com/client/v4";
const CF_API_ORIGIN = "https://api.cloudflare.com";
const CLOUDFLARE_OPAQUE_ID_RE = /^[0-9a-f]{16,64}$/i;
const ACCOUNTS_RESOURCE_RE =
  /^\/(?:workers\/domains(?:\/[0-9a-f]{16,64})?|pages\/projects\/ibex-harness-docs\/domains)$/;
const ZONES_RESOURCE_RE =
  /^\/[0-9a-f]{16,64}\/dns_records(?:\/[0-9a-f]{16,64})?$/;

export function requireEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
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

export async function cloudflareRequest(url, init = {}) {
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

export function accountUrl(suffix) {
  const accountId = requireEnv("CLOUDFLARE_ACCOUNT_ID");
  return buildAccountsApiUrl(accountId, suffix);
}

export async function listPagesDomains() {
  const result = await cloudflareRequest(
    accountUrl(`/pages/projects/${PAGES_PROJECT}/domains`),
  );
  return Array.isArray(result) ? result : [];
}

export async function attachPagesDomain(hostname, logPrefix = "[cf]") {
  const domains = await listPagesDomains();
  if (domains.some((entry) => entry.name === hostname)) {
    console.log(`${logPrefix} Pages domain already attached: ${hostname}`);
    return;
  }
  await cloudflareRequest(accountUrl(`/pages/projects/${PAGES_PROJECT}/domains`), {
    method: "POST",
    body: JSON.stringify({ name: hostname }),
  });
  console.log(`${logPrefix} attached ${hostname} to Pages project ${PAGES_PROJECT}`);
}

export async function detachPagesDomain(hostname, logPrefix = "[cf]") {
  const domains = await listPagesDomains();
  const match = domains.find((entry) => entry.name === hostname);
  if (!match) {
    console.log(`${logPrefix} Pages domain not attached: ${hostname}`);
    return;
  }
  await cloudflareRequest(
    accountUrl(`/pages/projects/${PAGES_PROJECT}/domains/${hostname}`),
    { method: "DELETE" },
  );
  console.log(`${logPrefix} detached ${hostname} from Pages project`);
}

export async function resolveZoneId(zoneName) {
  const zones = await cloudflareRequest(buildZonesLookupUrl(zoneName));
  const zone = Array.isArray(zones) ? zones[0] : undefined;
  if (!zone?.id) {
    throw new Error(`could not resolve Cloudflare zone for ${zoneName}`);
  }
  return assertCloudflareId(zone.id, "zone id");
}

async function listDnsRecords(hostname, zoneId) {
  const records = await cloudflareRequest(
    buildZonesApiUrl(
      zoneId,
      `/${zoneId}/dns_records`,
      `?name=${encodeURIComponent(hostname)}`,
    ),
  );
  return Array.isArray(records) ? records : [];
}

async function deleteDnsRecord(zoneId, recordId, logPrefix) {
  const id = assertCloudflareId(recordId, "dns record id");
  await cloudflareRequest(
    buildZonesApiUrl(zoneId, `/${zoneId}/dns_records/${id}`),
    { method: "DELETE" },
  );
  console.log(`${logPrefix} deleted DNS record ${id}`);
}

export async function removeConflictingDnsRecords(hostname, zoneId, logPrefix) {
  const existing = await listDnsRecords(hostname, zoneId);
  for (const record of existing) {
    if (record.type === "A" || record.type === "AAAA") {
      await deleteDnsRecord(zoneId, record.id, logPrefix);
    }
  }
}

export async function deleteHostnameDnsRecords(hostname, zoneId, logPrefix) {
  const existing = await listDnsRecords(hostname, zoneId);
  for (const record of existing) {
    await deleteDnsRecord(zoneId, record.id, logPrefix);
  }
}

export async function ensureCname(hostname, zoneId, target, logPrefix = "[cf]") {
  await removeConflictingDnsRecords(hostname, zoneId, logPrefix);

  const existing = await listDnsRecords(hostname, zoneId);
  const cname = existing.find((record) => record.type === "CNAME");

  if (cname?.content === target && cname.proxied === true) {
    console.log(`${logPrefix} DNS CNAME already points ${hostname} -> ${target}`);
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
    console.log(`${logPrefix} updated DNS CNAME for ${hostname}`);
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
  console.log(`${logPrefix} created DNS CNAME for ${hostname}`);
}
