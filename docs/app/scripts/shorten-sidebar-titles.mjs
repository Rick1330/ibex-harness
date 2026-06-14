#!/usr/bin/env node
/** Shorten sidebar titles; preserve full titles for page display. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { readYamlValue, setYamlField } from "./lib/yaml-frontmatter.mjs";
import {
  findYamlLine,
  readYamlLineValue,
  stripAfterDelimiter,
  stripParenthetical,
} from "./lib/text-utils.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../content/roadmap");

const STOP_WORDS = new Set(["and", "the", "with", "for", "a", "an"]);

const SHORT_WORDS = new Set(["api", "rls"]);

function titleCaseWord(word) {
  if (!word) return word;
  if (word.length <= 3 && !SHORT_WORDS.has(word)) {
    return word.toUpperCase();
  }
  return word.charAt(0).toUpperCase() + word.slice(1);
}

/** Derive a tight 2-word label from the file slug (e.g. 3.5.1-context-assembly-skeleton). */
function slugCompactName(slug, id) {
  const prefix = id.replace(/\./g, "-");
  const namePart = slug.startsWith(prefix)
    ? slug.slice(prefix.length).replace(/^-/, "")
    : slug.replace(/^[d]?\d+(?:-\d+)+-?/, "");
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
  let out = stripParenthetical(name);
  out = stripAfterDelimiter(out, "—");
  out = stripAfterDelimiter(out, ":");
  out = out.trim();

  if (out.length > 22) {
    out = out.split(" ").slice(0, 2).join(" ");
  }
  return out;
}

function parseMilestoneIdFromText(text) {
  const trimmed = text.trim();
  if (!trimmed) return undefined;
  const first = trimmed[0];
  if (first >= "0" && first <= "9") {
    const parts = trimmed.split(/[\s—–\-:]/)[0];
    return parts || undefined;
  }
  if (first === "d" || first === "D") {
    const parts = trimmed.split(/[\s—–\-:]/)[0];
    return parts.toLowerCase();
  }
  return undefined;
}

function shortenTitle(longTitle, milestoneId, filePath) {
  const normalized = filePath.replaceAll("\\", "/");
  const isMilestone = normalized.includes("/milestones/");

  if (isMilestone) {
    const slug = path.basename(filePath, ".mdx");
    const id =
      milestoneId ??
      parseMilestoneIdFromText(longTitle) ??
      parseMilestoneIdFromText(slug);

    if (!id) {
      return longTitle.length > 28 ? `${longTitle.slice(0, 26)}…` : longTitle;
    }

    const fromSlug = slugCompactName(slug, id);
    if (fromSlug) {
      return `${id} ${fromSlug}`.trim();
    }

    const stripped = longTitle.toLowerCase().startsWith("milestone ")
      ? longTitle.slice("milestone ".length).trim()
      : longTitle.trim();

    for (const delimiter of ["—", "–", "-"]) {
      const delimiterIndex = stripped.indexOf(delimiter);
      if (delimiterIndex !== -1) {
        const prefix = stripped.slice(0, delimiterIndex).trim();
        const suffix = stripped.slice(delimiterIndex + delimiter.length).trim();
        if (prefix) return `${prefix} ${compactName(suffix)}`.trim();
      }
    }

    return `${id} ${compactName(stripped)}`.trim();
  }

  if (longTitle.length <= 32) return longTitle;
  for (const delimiter of ["—", "–", "-"]) {
    const delimiterIndex = longTitle.indexOf(delimiter);
    if (delimiterIndex !== -1) return longTitle.slice(0, delimiterIndex).trim();
  }
  return longTitle;
}

function processFile(abs) {
  const raw = fs.readFileSync(abs, "utf8");
  const match = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
  if (!match) return;

  const fullTitleLine = findYamlLine(match[1], "fullTitle");
  const titleLine = findYamlLine(match[1], "title");
  if (!titleLine) return;

  const currentTitle = readYamlValue(readYamlLineValue(titleLine, "title") ?? "");
  const longTitle = fullTitleLine
    ? readYamlValue(readYamlLineValue(fullTitleLine, "fullTitle") ?? currentTitle)
    : currentTitle;

  const milestoneIdLine = findYamlLine(match[1], "milestoneId");
  const milestoneId = milestoneIdLine
    ? readYamlValue(readYamlLineValue(milestoneIdLine, "milestoneId") ?? "")
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
