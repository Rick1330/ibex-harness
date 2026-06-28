import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { loadEnvFile } from "./build-script-utils.mjs";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(scriptDir, "..");
const envPath = path.resolve(appRoot, "../../../ibexdepo/.env");
const DEPLOY_TIMEOUT_MS = Number(process.env.PAGES_DEPLOY_TIMEOUT_MS ?? 600_000);

const require = createRequire(import.meta.url);
const wranglerBin = path.join(
  path.dirname(require.resolve("wrangler/package.json")),
  "bin/wrangler.js",
);

function deployPages() {
  return new Promise((resolve, reject) => {
    console.log(
      `[deploy] uploading docs/app/out (timeout ${Math.round(DEPLOY_TIMEOUT_MS / 1000)}s)`,
    );
    const args = [
      wranglerBin,
      "pages",
      "deploy",
      "out",
      "--project-name=ibex-harness-docs",
      "--commit-dirty=true",
    ];
    const branch = process.env.PAGES_DEPLOY_BRANCH;
    if (branch) {
      args.push(`--branch=${branch}`);
    }

    const child = spawn(
      process.execPath,
      args,
      {
        cwd: appRoot,
        env: process.env,
        stdio: "inherit",
        shell: false,
      },
    );

    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(
        new Error(
          `wrangler pages deploy timed out after ${DEPLOY_TIMEOUT_MS}ms; retry or use GitHub Actions deploy`,
        ),
      );
    }, DEPLOY_TIMEOUT_MS);

    child.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });

    child.once("exit", (code) => {
      clearTimeout(timer);
      if (code === 0) resolve(undefined);
      else reject(new Error(`wrangler pages deploy exited with code ${code ?? "unknown"}`));
    });
  });
}

async function main() {
  const envCandidates = [
    envPath,
    path.resolve(appRoot, "../../../../ibexdepo/.env"),
  ];
  let loaded = false;
  for (const candidate of envCandidates) {
    try {
      loadEnvFile(candidate);
      loaded = true;
      console.log(`[deploy] loaded env from ${candidate}`);
      break;
    } catch {
      // try next candidate
    }
  }
  if (!loaded) {
    throw new Error(`No env file found (tried ${envCandidates.join(", ")})`);
  }
  if (!process.env.CLOUDFLARE_API_TOKEN || !process.env.CLOUDFLARE_ACCOUNT_ID) {
    throw new Error(
      "CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID required (see ibexdepo/.env)",
    );
  }
  await deployPages();
}

try {
  await main();
} catch (error) {
  console.error("[deploy] failed:", error.message);
  process.exit(1);
}
