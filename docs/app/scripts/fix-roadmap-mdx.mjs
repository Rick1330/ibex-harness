#!/usr/bin/env node
/** Fix MDX compatibility and frontmatter quality in roadmap content. */
import path from "node:path";
import { fileURLToPath } from "node:url";

import { fixFrontmatter } from "./lib/roadmap-frontmatter-fix.mjs";
import { readMdxParts, walkMdxFiles, writeMdxParts } from "./lib/mdx-walk.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../content/roadmap");

const ALLOWED_LANGS = new Set([
  "bash", "json", "javascript", "typescript", "tsx", "python", "yaml", "mdx",
  "go", "dockerfile", "sql", "xml", "text", "ini", "toml", "powershell", "sh",
  "mermaid",
]);

const LANG_ALIASES = {
  svg: "xml", makefile: "bash", make: "bash", css: "text",
  html: "text", proto: "text", grpc: "text", hcl: "text", env: "bash",
};

function normalizeLang(lang) {
  const lower = lang.toLowerCase();
  if (ALLOWED_LANGS.has(lower)) return lower;
  if (LANG_ALIASES[lower]) return LANG_ALIASES[lower];
  return "text";
}

function fixMetadataBlocks(body) {
  const lines = body.split("\n");
  for (let i = 0; i < lines.length - 1; i++) {
    if (/^\*\*[A-Za-z][A-Za-z0-9 /-]*:\*\*/.test(lines[i]) &&
        /^\*\*[A-Za-z][A-Za-z0-9 /-]*:\*\*/.test(lines[i + 1])) {
      if (!lines[i].endsWith("  ")) lines[i] = `${lines[i]}  `;
    }
  }
  return lines.join("\n");
}

function fixProsePart(part) {
  return fixMetadataBlocks(
    part
      .replace(/<(\d)/g, "&lt;$1")
      .replace(/\{(\d)/g, "&#123;$1")
      .replace(/<!--[\s\S]*?-->/g, ""),
  );
}

function fixCodeFence(part) {
  return part.replace(/^```([a-zA-Z0-9+#.-]+)/m, (_, lang) => `\`\`\`${normalizeLang(lang)}`);
}

function fixBody(body) {
  const parts = body.split(/(```[\s\S]*?```)/g);
  return parts
    .map((part, i) => (i % 2 === 1 ? fixCodeFence(part) : fixProsePart(part)))
    .join("");
}

function fixMdxFile(abs) {
  const parts = readMdxParts(abs);
  if (!parts) return;
  const body = fixBody(parts.body);
  const fm = fixFrontmatter(parts.fm, body);
  writeMdxParts(abs, fm, body);
}

walkMdxFiles(ROOT, fixMdxFile);
console.log("Fixed roadmap MDX files for MDX/Shiki compatibility and frontmatter");
