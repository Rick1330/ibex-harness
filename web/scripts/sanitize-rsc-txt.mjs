/**
 * Truncate Next.js static-export RSC prefetch `.txt` files.
 *
 * Cloudflare Pages content-negotiation can serve these as plain text when the
 * client router navigates to a `*.txt` URL. Empty stubs keep prefetch 200s
 * without leaking flight payloads. Root llms.txt and ai.txt are preserved.
 */
import { readdir, stat, truncate } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(scriptDir, "..", "out");

const PRESERVED_ROOT_FILES = new Set(["llms.txt", "ai.txt"]);

async function walkTxtFiles(dir, files = []) {
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch (error) {
    if (error?.code === "ENOENT") {
      return files;
    }
    throw error;
  }

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      await walkTxtFiles(fullPath, files);
      continue;
    }
    if (entry.isFile() && entry.name.endsWith(".txt")) {
      files.push(fullPath);
    }
  }
  return files;
}

function shouldPreserve(txtPath, root) {
  const relative = path.relative(root, txtPath);
  if (relative.includes("..")) {
    return false;
  }
  const parts = relative.split(path.sep);
  if (parts.length === 1) {
    return PRESERVED_ROOT_FILES.has(parts[0]);
  }
  return false;
}

export async function sanitizeRscTxtFiles(root = outDir) {
  const txtFiles = await walkTxtFiles(root);
  let sanitized = 0;

  for (const txtPath of txtFiles) {
    if (shouldPreserve(txtPath, root)) {
      continue;
    }
    const info = await stat(txtPath);
    if (info.size === 0) {
      continue;
    }
    await truncate(txtPath, 0);
    sanitized += 1;
  }

  return { total: txtFiles.length, sanitized };
}

async function main() {
  const outStat = await stat(outDir).catch(() => null);
  if (!outStat?.isDirectory()) {
    console.error(`[sanitize-rsc-txt] missing export directory: ${outDir}`);
    process.exit(1);
  }

  const { total, sanitized } = await sanitizeRscTxtFiles();
  console.log(
    `[sanitize-rsc-txt] scanned ${total} .txt file(s); truncated ${sanitized} RSC prefetch stub(s)`,
  );

  // Ensure preserved crawler files exist when present in public/.
  for (const name of PRESERVED_ROOT_FILES) {
    const preservedPath = path.join(outDir, name);
    const preservedStat = await stat(preservedPath).catch(() => null);
    if (preservedStat?.isFile() && preservedStat.size === 0) {
      console.warn(`[sanitize-rsc-txt] warning: ${name} is empty after export`);
    }
  }
}

const isMain =
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (isMain) {
  main().catch((error) => {
    console.error("[sanitize-rsc-txt] failed:", error);
    process.exit(1);
  });
}
