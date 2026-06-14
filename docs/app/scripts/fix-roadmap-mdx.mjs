#!/usr/bin/env node
/** Fix MDX compatibility and frontmatter quality in roadmap content. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  extractMarkdownField,
  matchYamlField,
  readYamlValue,
  setYamlField,
} from "./lib/yaml-frontmatter.mjs";

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

function describeComplete(title, completed) {
  if (!completed) return `${title} — complete.`;
  return `${title} — complete as of ${completed.replace(/\.$/, "")}.`;
}

function describeInProgress(title, milestone) {
  const current = milestone?.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
  if (!current) return `${title} — in progress.`;
  return `${title} — in progress. Current: ${current}.`;
}

function describePlanned(title, duration, depends) {
  const parts = [`${title} — planned.`];
  if (duration) parts.push(`Estimated ${duration.toLowerCase()}.`);
  if (depends) parts.push(`Depends on ${depends.toLowerCase()}.`);
  return parts.join(" ");
}

function cleanDescription(raw, title) {
  const text = raw.replace(/\\n/g, "\n").replace(/\*\*/g, "");
  if (!text.includes("Status:")) {
    return text.replace(/\s+/g, " ").trim();
  }

  const status =
    extractMarkdownField(text, "Status") ?? text.match(/Status:\s*([^\n]+)/i)?.[1]?.trim();
  const completed =
    extractMarkdownField(text, "Completed") ??
    text.match(/Completed:\s*([^\n]+)/i)?.[1]?.trim();
  const duration =
    extractMarkdownField(text, "Estimated duration") ??
    text.match(/Estimated duration:\s*([^\n]+)/i)?.[1]?.trim();
  const depends =
    extractMarkdownField(text, "Depends on") ??
    text.match(/Depends on:\s*([^\n]+)/i)?.[1]?.trim();
  const milestone =
    extractMarkdownField(text, "Current milestone") ??
    text.match(/Current milestone:\s*([^\n]+)/i)?.[1]?.trim();

  const lower = status?.toLowerCase() ?? "";
  if (lower.includes("complete")) return describeComplete(title, completed);
  if (lower.includes("progress")) return describeInProgress(title, milestone);
  if (lower.includes("planned")) return describePlanned(title, duration, depends);
  return text.replace(/\s+/g, " ").trim();
}

function fixFrontmatter(fm, body) {
  const titleMatch = fm.match(/^title:\s*(.+)$/m);
  const title = readYamlValue(titleMatch?.[1] ?? "Untitled");

  let out = fm;

  for (const key of ["description", "summary"]) {
    const match = matchYamlField(out, key);
    if (!match) continue;
    const val = readYamlValue(match[1]);
    if (
      val.includes("**") ||
      val.includes("\\n") ||
      /Status:/i.test(val) ||
      val.includes("Exit audit:")
    ) {
      out = setYamlField(out, key, cleanDescription(val, title));
    }
  }

  out = out.replace(/^completedDate:\s*.+$/m, (line) => {
    const val = readYamlValue(line.replace(/^completedDate:\s*/, ""));
    return `completedDate: ${JSON.stringify(val.replace(/\\n.*/, "").trim())}`;
  });

  const statusRaw =
    extractMarkdownField(body.slice(0, 800), "Status") ??
    extractMarkdownField(out, "Status");
  if (statusRaw && !/^status:/m.test(out)) {
    const lower = statusRaw.toLowerCase();
    if (lower.includes("complete")) out = setYamlField(out, "status", "completed");
    else if (lower.includes("progress")) out = setYamlField(out, "status", "in-progress");
    else if (lower.includes("planned")) out = setYamlField(out, "status", "planned");
  }

  const completed =
    extractMarkdownField(out, "Completed") ??
    extractMarkdownField(body.slice(0, 500), "Completed");
  if (completed && !/^completedDate:/m.test(out)) {
    out = setYamlField(out, "completedDate", completed);
  }

  return out;
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

function fixBody(body) {
  const parts = body.split(/(```[\s\S]*?```)/g);
  return parts
    .map((part, i) => {
      if (i % 2 === 1) {
        return part.replace(/^```([a-zA-Z0-9+#.-]+)/m, (_, lang) => `\`\`\`${normalizeLang(lang)}`);
      }
      return fixMetadataBlocks(
        part
          .replace(/<(\d)/g, "&lt;$1")
          .replace(/\{(\d)/g, "&#123;$1")
          .replace(/<!--[\s\S]*?-->/g, ""),
      );
    })
    .join("");
}

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(abs);
    else if (entry.name.endsWith(".mdx")) {
      const raw = fs.readFileSync(abs, "utf8");
      const match = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
      if (!match) continue;
      const body = fixBody(match[2]);
      const fm = fixFrontmatter(match[1], body);
      fs.writeFileSync(abs, `---\n${fm}\n---\n${body}`, "utf8");
    }
  }
}

walk(ROOT);
console.log("Fixed roadmap MDX files for MDX/Shiki compatibility and frontmatter");
