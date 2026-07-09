import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { generateOgImages } from "./generate-og-images.mjs";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(scriptDir, "..");
const publicDir = path.join(appRoot, "public");
const buildIdPath = path.join(appRoot, ".next", "BUILD_ID");
const EXTRACT_PORT = Number(process.env.SEARCH_EXTRACT_PORT ?? 34567);
const MAX_INDEX_BYTES = Number(process.env.SEARCH_INDEX_MAX_BYTES ?? 5_000_000);

const require = createRequire(import.meta.url);
const nextBin = path.join(
  path.dirname(require.resolve("next/package.json")),
  "dist/bin/next",
);

async function buildExists() {
  try {
    await access(buildIdPath);
    return true;
  } catch {
    return false;
  }
}

function isServerReady(text) {
  return text.includes("Ready") || text.includes("started server");
}

function waitForReady(child, timeoutMs = 120_000) {
  return new Promise((resolve, reject) => {
    let output = "";
    const timer = setTimeout(() => {
      reject(new Error(`next start did not become ready within ${timeoutMs}ms`));
    }, timeoutMs);

    const onData = (chunk) => {
      output += chunk.toString();
      if (!isServerReady(output)) return;
      clearTimeout(timer);
      child.stdout?.off("data", onData);
      child.stderr?.off("data", onData);
      child.off("exit", onExit);
      resolve(undefined);
    };

    const onExit = (code) => {
      clearTimeout(timer);
      const detail = child.stderrBuffer?.() ?? "";
      const codeLabel = code ?? "unknown";
      const detailSuffix = detail ? `: ${detail.trim()}` : "";
      reject(
        new Error(`next start exited with code ${codeLabel} before ready${detailSuffix}`),
      );
    };

    child.stdout?.on("data", onData);
    child.stderr?.on("data", onData);
    child.once("error", reject);
    child.once("exit", onExit);
  });
}

async function fetchSearchIndex(port) {
  const response = await fetch(`http://127.0.0.1:${port}/api/search`, {
    signal: AbortSignal.timeout(120_000),
    redirect: "manual",
  });
  if (!response.ok) {
    throw new Error(`/api/search returned HTTP ${response.status}`);
  }
  const body = await response.text();
  if (body.length < 1000 || body === "[]") {
    throw new Error(
      `/api/search response too small (${body.length} bytes); expected prerendered Orama export`,
    );
  }
  if (body.length > MAX_INDEX_BYTES) {
    throw new Error(
      `search index too large (${body.length} bytes); max ${MAX_INDEX_BYTES}`,
    );
  }
  return body;
}

function spawnNextStart(port) {
  const child = spawn(process.execPath, [nextBin, "start", "-p", String(port)], {
    cwd: appRoot,
    env: { ...process.env, PORT: String(port), SEARCH_EXTRACT: "1" },
    stdio: ["ignore", "pipe", "pipe"],
    shell: false,
  }); // nosemgrep: javascript.lang.security.detect-child-process.detect-child-process

  let stderr = "";
  child.stderr?.on("data", (chunk) => {
    stderr += chunk.toString();
    process.stderr.write(chunk);
  });

  child.stderrBuffer = () => stderr;
  return child;
}

async function writeIndexArtifacts(body, buildId) {
  const targets = [
    path.join(publicDir, "search-index.json"),
    path.join(publicDir, `search-index.${buildId}.json`),
  ];

  await Promise.all(
    targets.map(async (target) => {
      await mkdir(path.dirname(target), { recursive: true });
      await writeFile(target, body, "utf8");
      console.log(`[search] wrote ${target} (${body.length} bytes)`);
    }),
  );
}

async function tryExtractOnPort(port, buildId) {
  const child = spawnNextStart(port);
  try {
    await waitForReady(child);
    const body = await fetchSearchIndex(port);
    await writeIndexArtifacts(body, buildId);
    await generateOgImages(port);
    return true;
  } catch (error) {
    if (!String(error).includes("EADDRINUSE")) {
      throw error;
    }
    console.warn(`[search] port ${port} in use, trying next port`);
    return false;
  } finally {
    child.kill("SIGTERM");
  }
}

async function extractToPublic(preferredPort) {
  const buildId = (await readFile(buildIdPath, "utf8")).trim();
  const ports = [preferredPort, preferredPort + 1, preferredPort + 2, preferredPort + 3];

  for (const port of ports) {
    if (await tryExtractOnPort(port, buildId)) {
      return;
    }
  }

  throw new Error("search extract failed: all ports in use");
}

async function main() {
  if (!(await buildExists())) {
    throw new Error(
      "Cannot extract search index: .next/BUILD_ID missing. Run next build first.",
    );
  }
  await extractToPublic(EXTRACT_PORT);
}

main().catch((error) => {
  console.error("[search] extract failed:", error);
  process.exit(1);
});
