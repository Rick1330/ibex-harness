/**
 * Attach ibexharness.com (apex) to Cloudflare Pages and remove docs.ibexharness.com.
 *
 * Prerequisites: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID
 *
 * After running:
 * 1. Add a Cloudflare Redirect Rule: docs.ibexharness.com/* → https://ibexharness.com/$1 (301)
 * 2. Verify: bash .github/scripts/docs-smoke.sh https://ibexharness.com
 */
import process from "node:process";

import {
  attachPagesDomain,
  deleteHostnameDnsRecords,
  detachPagesDomain,
  ensureCname,
  PAGES_CNAME_TARGET,
  resolveZoneId,
} from "./lib/cloudflare-pages-api.mjs";

const APEX_HOST = "ibexharness.com";
const LEGACY_DOCS_HOST = "docs.ibexharness.com";
const ZONE_NAME = "ibexharness.com";
const LOG = "[apex-cutover]";

async function main() {
  console.log(`${LOG} attaching ${APEX_HOST} to Cloudflare Pages`);
  const zoneId = await resolveZoneId(ZONE_NAME);

  await attachPagesDomain(APEX_HOST, LOG);
  await ensureCname(APEX_HOST, zoneId, PAGES_CNAME_TARGET, LOG);

  await detachPagesDomain(LEGACY_DOCS_HOST, LOG);
  await deleteHostnameDnsRecords(LEGACY_DOCS_HOST, zoneId, LOG);

  console.log(
    `${LOG} complete — add zone Redirect Rule: ${LEGACY_DOCS_HOST}/* → https://${APEX_HOST}/$1 (301)`,
  );
}

try {
  await main();
} catch (err) {
  const message = err instanceof Error ? err.message : String(err);
  console.error(`${LOG} failed: ${message}`);
  process.exit(1);
}
