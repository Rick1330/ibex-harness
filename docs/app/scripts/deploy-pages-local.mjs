import { readFileSync } from "node:fs";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(scriptDir, "..");
const envPath = path.resolve(appRoot, "../../../ibexdepo/.env");
const DEPLOY_TIMEOUT_MS = Number(process.env.PAGES_DEPLOY_TIMEOUT_MS ?? 600_000);

const require = createRequire(import.meta.url);
const wranglerBin = path.join(
  path.dirname(require.resolve("wrangler/package.json")),
  "bin/wrangler.js",
);

function loadEnvFile(filePath) {
  let content = readFileSync(filePath, "utf8");
  if (content.charCodeAt(0) === 0xfeff) {
    content = content.slice(1);
  }
  for (const rawLine of content.split("\n")) {
    const line = rawLine.replace(/\r$/, "");
    const match = line.match(/^([^#=]+)=(.*)$/);
    if (!match) continue;
    const key = match[1].trim().replace(/\r$/, "");
    let value = match[2].trim().replace(/\r$/, "");
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    process.env[key] = value;
  }
}

function deployPages() {
  return new Promise((resolve, reject) => {
    console.log(
      `[deploy] uploading docs/app/out (timeout ${Math.round(DEPLOY_TIMEOUT_MS / 1000)}s)`,
    );
    const child = spawn(
      process.execPath,
      [
        wranglerBin,
        "pages",
        "deploy",
        "out",
        "--project-name=ibex-harness-docs",
        "--branch=main",
        "--commit-dirty=true",
      ],
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

main().catch((error) => {
  console.error("[deploy] failed:", error.message);
  process.exit(1);
});
