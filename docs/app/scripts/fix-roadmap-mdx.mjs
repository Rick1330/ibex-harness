#!/usr/bin/env node
/** Fix MDX compatibility and frontmatter quality in roadmap content. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../content/roadmap");

const ALLOWED_LANGS = new Set([
  "bash", "json", "javascript", "typescript", "tsx", "python", "yaml", "mdx",
  "go", "dockerfile", "sql", "xml", "text", "ini", "toml", "powershell", "sh",
]);

const LANG_ALIASES = {
  svg: "xml", makefile: "bash", make: "bash", mermaid: "text", css: "text",
  html: "text", proto: "text", grpc: "text", hcl: "text", env: "bash",
};

function normalizeLang(lang) {
  const lower = lang.toLowerCase();
  if (ALLOWED_LANGS.has(lower)) return lower;
  if (LANG_ALIASES[lower]) return LANG_ALIASES[lower];
  return "text";
}

function extractField(text, label) {
  const re = new RegExp(`\\*\\*${label}:\\*\\*\\s*([^\\n*]+)`, "i");
  return text.match(re)?.[1]?.trim();
}

function cleanDescription(raw, title) {
  const text = raw.replace(/\\n/g, "\n").replace(/\*\*/g, "");
  if (!text.includes("Status:") && !text.includes("Status:")) {
    return text.replace(/\s+/g, " ").trim();
  }

  const status = extractField(text, "Status") ?? text.match(/Status:\s*([^\n]+)/i)?.[1]?.trim();
  const completed = extractField(text, "Completed") ?? text.match(/Completed:\s*([^\n]+)/i)?.[1]?.trim();
  const duration = extractField(text, "Estimated duration") ?? text.match(/Estimated duration:\s*([^\n]+)/i)?.[1]?.trim();
  const depends = extractField(text, "Depends on") ?? text.match(/Depends on:\s*([^\n]+)/i)?.[1]?.trim();
  const milestone = extractField(text, "Current milestone") ?? text.match(/Current milestone:\s*([^\n]+)/i)?.[1]?.trim();

  if (status?.toLowerCase().includes("complete")) {
    return completed
      ? `${title} — complete as of ${completed.replace(/\.$/, "")}.`
      : `${title} — complete.`;
  }
  if (status?.toLowerCase().includes("progress")) {
    const current = milestone?.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
    return current
      ? `${title} — in progress. Current: ${current}.`
      : `${title} — in progress.`;
  }
  if (status?.toLowerCase().includes("planned")) {
    const parts = [`${title} — planned.`];
    if (duration) parts.push(`Estimated ${duration.toLowerCase()}.`);
    if (depends) parts.push(`Depends on ${depends.toLowerCase()}.`);
    return parts.join(" ");
  }
  return text.replace(/\s+/g, " ").trim();
}

function readYamlValue(raw) {
  const trimmed = raw.trim();
  if (trimmed.startsWith('"') || trimmed.startsWith("'")) {
    try {
      return JSON.parse(trimmed.startsWith('"') ? trimmed : `"${trimmed.slice(1, -1)}"`);
    } catch {
      return trimmed.replace(/^"|"$/g, "");
    }
  }
  return trimmed.replace(/^"|"$/g, "");
}

function setYamlField(fm, key, value) {
  const re = new RegExp(`^${key}:\\s*.+$`, "m");
  const line = `${key}: ${JSON.stringify(value)}`;
  if (re.test(fm)) return fm.replace(re, line);
  return `${fm}\n${line}`;
}

function fixFrontmatter(fm, body) {
  const titleMatch = fm.match(/^title:\s*(.+)$/m);
  const title = readYamlValue(titleMatch?.[1] ?? "Untitled");

  let out = fm;

  for (const key of ["description", "summary"]) {
    const match = out.match(new RegExp(`^${key}:\\s*(.+)$`, "m"));
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
    extractField(body.slice(0, 800), "Status") ??
    extractField(out, "Status");
  if (statusRaw && !/^status:/m.test(out)) {
    const lower = statusRaw.toLowerCase();
    if (lower.includes("complete")) out = setYamlField(out, "status", "completed");
    else if (lower.includes("progress")) out = setYamlField(out, "status", "in-progress");
    else if (lower.includes("planned")) out = setYamlField(out, "status", "planned");
  }

  const completed =
    extractField(out, "Completed") ??
    extractField(body.slice(0, 500), "Completed");
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
