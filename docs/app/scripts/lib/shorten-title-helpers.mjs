/** Title shortening helpers for roadmap sidebar labels. */

import path from "node:path";

import {
  stripAfterDelimiter,
  stripParenthetical,
} from "./text-utils.mjs";

const STOP_WORDS = new Set(["and", "the", "with", "for", "a", "an"]);
const SHORT_WORDS = new Set(["api", "rls"]);
const TITLE_DELIMITERS = ["—", "–", "-"];

export function titleCaseWord(word) {
  if (!word) return word;
  if (word.length <= 3 && !SHORT_WORDS.has(word)) {
    return word.toUpperCase();
  }
  return word.charAt(0).toUpperCase() + word.slice(1);
}

function stripLeadingDash(value) {
  return value.startsWith("-") ? value.slice(1) : value;
}

function stripNumericSlugPrefix(slug) {
  let index = 0;
  if (slug[index] === "d" || slug[index] === "D") index += 1;

  while (index < slug.length && slug[index] >= "0" && slug[index] <= "9") {
    index += 1;
  }

  if (index < slug.length && slug[index] === "-") index += 1;
  while (index < slug.length && slug[index] >= "0" && slug[index] <= "9") {
    index += 1;
  }

  if (index < slug.length && slug[index] === "-") index += 1;
  return stripLeadingDash(slug.slice(index));
}

export function slugCompactName(slug, id) {
  const prefix = id.replaceAll(".", "-");
  const namePart = slug.startsWith(prefix)
    ? stripLeadingDash(slug.slice(prefix.length))
    : stripNumericSlugPrefix(slug);

  const words = namePart
    .split("-")
    .filter((word) => word && !STOP_WORDS.has(word));

  if (words.length === 0) {
    return namePart.replaceAll("-", " ");
  }

  return words.slice(0, 2).map(titleCaseWord).join(" ");
}

export function compactName(name) {
  let out = stripParenthetical(name);
  out = stripAfterDelimiter(out, "—");
  out = stripAfterDelimiter(out, ":");
  out = out.trim();

  if (out.length > 22) {
    return out.split(" ").slice(0, 2).join(" ");
  }
  return out;
}

function firstTokenBeforeDelimiter(text) {
  for (const delimiter of TITLE_DELIMITERS) {
    const index = text.indexOf(delimiter);
    if (index !== -1) return text.slice(0, index).trim();
  }
  return text.trim();
}

export function parseMilestoneIdFromText(text) {
  return firstTokenBeforeDelimiter(text.trim()) || undefined;
}

function splitTitleOnDelimiter(text) {
  for (const delimiter of TITLE_DELIMITERS) {
    const index = text.indexOf(delimiter);
    if (index === -1) continue;
    return {
      prefix: text.slice(0, index).trim(),
      suffix: text.slice(index + delimiter.length).trim(),
    };
  }
  return undefined;
}

export function shortenMilestoneTitle(longTitle, milestoneId, filePath) {
  const slug = path.basename(filePath, ".mdx");
  const id =
    milestoneId ??
    parseMilestoneIdFromText(longTitle) ??
    parseMilestoneIdFromText(slug);

  if (!id) {
    return longTitle.length > 28 ? `${longTitle.slice(0, 26)}…` : longTitle;
  }

  const fromSlug = slugCompactName(slug, id);
  if (fromSlug) return `${id} ${fromSlug}`.trim();

  const stripped = longTitle.toLowerCase().startsWith("milestone ")
    ? longTitle.slice("milestone ".length).trim()
    : longTitle.trim();

  const split = splitTitleOnDelimiter(stripped);
  if (split?.prefix) {
    return `${split.prefix} ${compactName(split.suffix)}`.trim();
  }

  return `${id} ${compactName(stripped)}`.trim();
}

export function shortenDefaultTitle(longTitle) {
  if (longTitle.length <= 32) return longTitle;
  return firstTokenBeforeDelimiter(longTitle);
}

export function shortenTitle(longTitle, milestoneId, filePath) {
  const normalized = filePath.replaceAll("\\", "/");
  if (normalized.includes("/milestones/")) {
    return shortenMilestoneTitle(longTitle, milestoneId, filePath);
  }
  return shortenDefaultTitle(longTitle);
}
