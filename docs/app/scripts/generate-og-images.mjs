import { mkdir, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(scriptDir, "..");
const publicDir = path.join(appRoot, "public");
const docsContentDir = path.join(appRoot, "content", "docs");

async function walkMdxFiles(dir) {
  const files = [];
  async function walk(current) {
    for (const entry of await readdir(current, { withFileTypes: true })) {
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        await walk(fullPath);
        continue;
      }
      if (entry.name.endsWith(".mdx") || entry.name.endsWith(".md")) {
        files.push(fullPath);
      }
    }
  }
  await walk(dir);
  return files;
}

function filePathToSlugSegments(filePath) {
  const relative = path.relative(docsContentDir, filePath).replaceAll("\\", "/");
  const withoutExt = relative.replace(/\.(mdx|md)$/, "");
  if (withoutExt === "index") {
    return [];
  }
  if (withoutExt.endsWith("/index")) {
    return withoutExt.slice(0, -"/index".length).split("/").filter(Boolean);
  }
  return withoutExt.split("/").filter(Boolean);
}

async function loadDocSlugs() {
  const files = await walkMdxFiles(docsContentDir);
  return files.map((filePath) => filePathToSlugSegments(filePath));
}

async function fetchOgPng(port, slugPath) {
  const url = `http://127.0.0.1:${port}/api/og/${slugPath}`;
  const response = await fetch(url, {
    signal: AbortSignal.timeout(60_000),
    redirect: "manual",
  });
  if (!response.ok) {
    throw new Error(`${url} returned HTTP ${response.status}`);
  }
  return Buffer.from(await response.arrayBuffer());
}

async function writeOgImage(slugSegments, png) {
  const relativeDir = path.join("docs", ...slugSegments);
  const targetDir = path.join(publicDir, relativeDir);
  await mkdir(targetDir, { recursive: true });
  const target = path.join(targetDir, "opengraph-image.png");
  await writeFile(target, png);
  console.log(`[og] wrote ${target} (${png.length} bytes)`);
}

export async function generateOgImages(port) {
  const slugSegmentsList = await loadDocSlugs();
  console.log(`[og] generating ${slugSegmentsList.length} images`);

  for (const slugSegments of slugSegmentsList) {
    const slugPath = slugSegments.join("/");
    const png = await fetchOgPng(port, slugPath);
    await writeOgImage(slugSegments, png);
  }
}
