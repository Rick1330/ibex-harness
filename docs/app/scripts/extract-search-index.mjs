import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { access } from "node:fs/promises";
import { writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(scriptDir, "..");
const outputPath = path.join(appRoot, "public", "search-index.json");
const buildIdPath = path.join(appRoot, ".next", "BUILD_ID");
const DEFAULT_PORTS = [34567, 34568, 34569, 34570];

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

function waitForReady(child, timeoutMs = 120_000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`next start did not become ready within ${timeoutMs}ms`));
    }, timeoutMs);

    const onData = (chunk) => {
      const text = chunk.toString();
      if (text.includes("Ready") || text.includes("started server")) {
        clearTimeout(timer);
        child.stdout?.off("data", onData);
        child.stderr?.off("data", onData);
        resolve(undefined);
      }
    };

    child.stdout?.on("data", onData);
    child.stderr?.on("data", onData);
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code !== 0 && code !== null) {
        clearTimeout(timer);
        reject(new Error(`next start exited with code ${code}`));
      }
    });
  });
}

async function fetchSearchIndex(port) {
  const response = await fetch(`http://127.0.0.1:${port}/api/search`, {
    signal: AbortSignal.timeout(120_000),
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
  return body;
}

async function startAndExtract(port) {
  const child = spawn(process.execPath, [nextBin, "start", "-p", String(port)], {
    cwd: appRoot,
    env: { ...process.env, PORT: String(port), SEARCH_EXTRACT: "1" },
    stdio: ["ignore", "pipe", "pipe"],
    shell: false,
  });

  try {
    await waitForReady(child);
    const body = await fetchSearchIndex(port);
    await writeFile(outputPath, body, "utf8");
    console.log(`[search] wrote ${outputPath} (${body.length} bytes)`);
  } finally {
    child.kill("SIGTERM");
  }
}

async function main() {
  if (!(await buildExists())) {
    throw new Error(
      "Cannot extract search index: .next/BUILD_ID missing. Run next build first.",
    );
  }

  const ports = process.env.SEARCH_EXTRACT_PORT
    ? [Number(process.env.SEARCH_EXTRACT_PORT)]
    : DEFAULT_PORTS;

  let lastError;
  for (const port of ports) {
    try {
      await startAndExtract(port);
      return;
    } catch (error) {
      lastError = error;
      if (!String(error).includes("EADDRINUSE") && !String(error).includes("exit")) {
        throw error;
      }
    }
  }

  throw lastError ?? new Error("search index extract failed on all ports");
}

main().catch((error) => {
  console.error("[search] extract failed:", error);
  process.exit(1);
});
