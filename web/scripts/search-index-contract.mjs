import { access } from "node:fs/promises";
import path from "node:path";

const requiredDocuments = new Map([
  ["/docs/adr/0081-fail-closed-proxy-runtime-controls", "SERVICE_DEGRADED"],
  ["/roadmap/phase-4-multi-provider/findings", "F4-037"],
  ["/roadmap/phase-4-multi-provider/risks", "Redis"],
]);
const excludedMilestone =
  "/roadmap/phase-4-multi-provider/milestones/4.p.0-runtime-topology-environment-contract";

async function assertSearchIndexContract(body, { routeRoot } = {}) {
  const docs = documentsFromBody(body);
  const byUrl = new Map(docs.map((doc) => [doc.url, doc]));
  for (const [url, token] of requiredDocuments) {
    await assertRequiredDocument(byUrl, routeRoot, url, token);
  }
  assertNoExcludedDocuments(byUrl);
}

function documentsFromBody(body) {
  const storedDocs = JSON.parse(body)?.docs?.docs;
  if (Array.isArray(storedDocs)) return storedDocs;
  if (storedDocs && typeof storedDocs === "object") return Object.values(storedDocs);
  throw new Error("search index does not contain the expected Orama document collection");
}

async function assertRequiredDocument(byUrl, routeRoot, url, token) {
  const doc = byUrl.get(url);
  if (!doc || typeof doc !== "object") {
    throw new Error(`required search document is missing: ${url}`);
  }
  const searchable = `${doc.title ?? ""}\n${doc.description ?? ""}\n${doc.content ?? ""}`;
  if (!searchable.toLowerCase().includes(token.toLowerCase())) {
    throw new Error(`search document ${url} is missing its required token ${token}`);
  }
  const routeArtifact = path.join(
    routeRoot,
    ".next",
    "server",
    "app",
    `${url.slice(1)}.html`,
  );
  try {
    await access(routeArtifact);
  } catch {
    throw new Error(`search document ${url} has no compiled route artifact`);
  }
}

function assertNoExcludedDocuments(byUrl) {
  if (byUrl.has(excludedMilestone)) {
    throw new Error(`dense milestone unexpectedly included in search index: ${excludedMilestone}`);
  }
}

export { assertSearchIndexContract };
