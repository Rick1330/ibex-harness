#!/usr/bin/env node
/** Shorten sidebar titles; preserve full titles for page display. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../content/roadmap");

const STOP_WORDS = new Set(["and", "the", "with", "for", "a", "an"]);

function readYamlValue(raw) {
  const trimmed = raw.trim();
  try {
    return JSON.parse(trimmed.startsWith('"') ? trimmed : `"${trimmed}"`);
  } catch {
    return trimmed.replace(/^["']|["']$/g, "");
  }
}

function setYamlField(fm, key, value) {
  const re = new RegExp(`^${key}:\\s*.+$`, "m");
  const line = `${key}: ${JSON.stringify(value)}`;
  if (re.test(fm)) return fm.replace(re, line);
  return `${fm}\n${line}`;
}

function titleCaseWord(word) {
  if (!word) return word;
  if (word.length <= 3 && word !== "api" && word !== "rls") {
    return word.toUpperCase();
  }
  return word.charAt(0).toUpperCase() + word.slice(1);
}

/** Derive a tight 2-word label from the file slug (e.g. 3.5.1-context-assembly-skeleton). */
function slugCompactName(slug, id) {
  const escaped = id.replace(/\./g, "\\.");
  const namePart = slug.replace(new RegExp(`^${escaped}-?`), "");
  const words = namePart
    .split("-")
    .filter((w) => w && !STOP_WORDS.has(w));

  if (words.length === 0) {
    return namePart.replace(/-/g, " ");
  }

  return words
    .slice(0, 2)
    .map(titleCaseWord)
    .join(" ");
}

function compactName(name) {
  let out = name
    .replace(/\s*\([^)]*\)/g, "")
    .replace(/\s*—\s*.+$/, "")
    .replace(/\s*:\s*.+$/, "")
    .trim();

  if (out.length > 22) {
    const words = out.split(/\s+/);
    out = words.slice(0, 2).join(" ");
  }
  return out;
}

function shortenTitle(longTitle, milestoneId, filePath) {
  const normalized = filePath.replace(/\\/g, "/");
  const isMilestone = normalized.includes("/milestones/");

  if (isMilestone) {
    const slug = path.basename(filePath, ".mdx");
    const id =
      milestoneId ??
      longTitle.match(/^(?:Milestone\s+)?([d]?\d+\.\d+(?:\.\d+)?)/i)?.[1] ??
      slug.match(/^([d]?\d+\.\d+(?:\.\d+)?)/)?.[1];

    if (!id) {
      return longTitle.length > 28 ? `${longTitle.slice(0, 26)}…` : longTitle;
    }

    const fromSlug = slugCompactName(slug, id);
    if (fromSlug) {
      return `${id} ${fromSlug}`.trim();
    }

    const stripped = longTitle.replace(/^Milestone\s+/i, "").trim();
    const dashMatch = stripped.match(/^([d]?\d+\.\d+(?:\.\d+)?)\s*[—–\-]\s*(.+)$/);
    if (dashMatch) {
      return `${dashMatch[1]} ${compactName(dashMatch[2])}`.trim();
    }

    return `${id} ${compactName(stripped.replace(/^[d]?\d+\.\d+(?:\.\d+)?\s*[—–\-]\s*/, ""))}`.trim();
  }

  if (longTitle.length <= 32) return longTitle;
  return longTitle.split(/\s*[—–\-]\s+/)[0].trim();
}

function processFile(abs) {
  const raw = fs.readFileSync(abs, "utf8");
  const match = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
  if (!match) return;

  const fullTitleMatch = match[1].match(/^fullTitle:\s*(.+)$/m);
  const titleMatch = match[1].match(/^title:\s*(.+)$/m);
  if (!titleMatch) return;

  const currentTitle = readYamlValue(titleMatch[1]);
  const longTitle = fullTitleMatch
    ? readYamlValue(fullTitleMatch[1])
    : currentTitle;

  const milestoneIdMatch = match[1].match(/^milestoneId:\s*(.+)$/m);
  const milestoneId = milestoneIdMatch
    ? readYamlValue(milestoneIdMatch[1])
    : undefined;

  const short = shortenTitle(longTitle, milestoneId, abs);

  let fm = match[1];
  if (!fm.includes("fullTitle:") && longTitle !== short) {
    fm = setYamlField(fm, "fullTitle", longTitle);
  }
  fm = setYamlField(fm, "title", short);

  fs.writeFileSync(abs, `---\n${fm}\n---\n${match[2]}`, "utf8");
}

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(abs);
    else if (entry.name.endsWith(".mdx")) processFile(abs);
  }
}

walk(ROOT);
console.log("Shortened roadmap sidebar titles");
