#!/usr/bin/env node
/** Strip internal prompt/workspace paths from public content. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOTS = [
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../content/docs"),
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../content/roadmap"),
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../content/blog"),
];

function sanitizeBody(body) {
  let out = body;

  out = out.replace(
    /## Execution prompt\s*\n[\s\S]*?(?=\n## |\n---\s*\n|$)/gi,
    "",
  );

  out = out.replace(
    /- \[x\] Execution prompt[^\n]*/gi,
    "- [x] Contributor execution materials prepared",
  );
  out = out.replace(
    /- \[x\] Add execution prompt[^\n]*/gi,
    "- [x] Contributor execution materials prepared",
  );
  out = out.replace(
    /- \[x\] Update[^\n]*execution prompt[^\n]*/gi,
    "- [x] Contributor documentation updated",
  );

  out = out.replace(/`ibex-harness-workspace\/prompts\/[^`]*`/g, "contributor workspace");
  out = out.replace(/ibex-harness-workspace\/prompts\//g, "contributor workspace");
  out = out.replace(/under `ibex-harness-workspace\/prompts\/`/g, "in the contributor workspace");
  out = out.replace(
    /\| `ibex-harness-workspace\/prompts\/[^|]*` \| [^\n]*/g,
    "| Contributor workspace | Add |",
  );

  out = out.replace(
    /\[([^\]]*)\]\(\/roadmap\/prompts\/[^)]+\)/g,
    "",
  );
  out = out.replace(/See \[MILESTONE-[^\]]+\]\(\/roadmap\/prompts\/[^)]+\)\.?/g, "");

  out = out.replace(
    /Execution prompts relocated to the local workspace \(`ibex-harness-workspace\/prompts\/`\) — not published/g,
    "Execution prompts are not published on the public site.",
  );
  out = out.replace(
    /`ibex-harness-workspace\/archive\/foundation\/`/g,
    "contributor workspace archive",
  );
  out = out.replace(/ibex-harness-workspace\/archive\/foundation\//g, "contributor workspace archive");

  return out.replace(/\n{3,}/g, "\n\n");
}

function sanitizeFrontmatter(fm) {
  return fm
    .replace(/ibex-harness-workspace\/prompts\//g, "contributor workspace")
    .replace(/ibex-harness-workspace\/archive\/foundation\//g, "contributor workspace archive")
    .replace(/`ibex-harness-workspace\/[^`]*`/g, "contributor workspace")
    .replace(/\/roadmap\/prompts\//g, "");
}

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(abs);
    else if (entry.name.endsWith(".mdx")) {
      const raw = fs.readFileSync(abs, "utf8");
      const match = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
      if (!match) continue;
      const fm = sanitizeFrontmatter(match[1]);
      const body = sanitizeBody(match[2]);
      fs.writeFileSync(abs, `---\n${fm}\n---\n${body}`, "utf8");
    }
  }
}

for (const root of ROOTS) {
  if (fs.existsSync(root)) walk(root);
}
console.log("Sanitized public content (prompt/workspace paths)");
