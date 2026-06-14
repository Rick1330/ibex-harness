#!/usr/bin/env node
/** Shorten sidebar titles; preserve full titles for page display. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { readYamlValue, setYamlField } from "./lib/yaml-frontmatter.mjs";
import { shortenTitle } from "./lib/shorten-title-helpers.mjs";
import {
  findYamlLine,
  readYamlLineValue,
} from "./lib/text-utils.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../content/roadmap");

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
