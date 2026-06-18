import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outDir = path.join(appRoot, "public", "markdown");

const FRONTMATTER_PATTERN = /^---\r?\n[\s\S]*?\r?\n---\r?\n?/;

const SECTIONS = [
  { name: "docs", dir: path.join(appRoot, "content", "docs") },
  { name: "roadmap", dir: path.join(appRoot, "content", "roadmap") },
  { name: "blog", dir: path.join(appRoot, "content", "blog") },
];

function stripMdxFrontmatter(raw) {
  return raw.replace(FRONTMATTER_PATTERN, "").trimStart();
}

function getMarkdownExportId(section, relativePath) {
  const key = `${section}/${relativePath.replaceAll("\\", "/")}`;
  return Buffer.from(key, "utf8").toString("base64url");
}

function walkMdxFiles(dir, files = []) {
  if (!fs.existsSync(dir)) return files;

  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walkMdxFiles(fullPath, files);
      continue;
    }
    if (entry.isFile() && entry.name.endsWith(".mdx")) {
      files.push(fullPath);
    }
  }

  return files;
}

fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(outDir, { recursive: true });

let exported = 0;

for (const { name: section, dir } of SECTIONS) {
  for (const filePath of walkMdxFiles(dir)) {
    const relative = path.relative(dir, filePath).replaceAll("\\", "/");
    const body = stripMdxFrontmatter(fs.readFileSync(filePath, "utf8"));
    const id = getMarkdownExportId(section, relative);
    fs.writeFileSync(path.join(outDir, `${id}.md`), body, "utf8");
    exported += 1;
  }
}

console.log(`Exported ${exported} markdown files to public/markdown/`);
