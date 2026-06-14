#!/usr/bin/env node
/** Repair internal roadmap links for the public docs site. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { rewriteMarkdownLinks } from "./lib/markdown-link-rewrite.mjs";
import {
  isAdrPath,
  resolveRoadmapLinkTarget,
} from "./lib/roadmap-link-target.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../content/roadmap");

const ADR_SLUGS = new Map([
  ["ADR-0002-repo-foundation-bootstrap.md", "0002-repo-foundation-bootstrap"],
  ["ADR-0003-branch-protection-and-merge-policy.md", "0003-branch-protection-and-merge-policy"],
  ["ADR-0004-protobuf-and-codegen-policy.md", "0004-protobuf-and-codegen-policy"],
  ["ADR-0005-postgres-migration-strategy.md", "0005-postgres-migration-strategy"],
  ["ADR-0006-auth-proto-contract.md", "0006-auth-proto-contract"],
  ["ADR-0007-auth-token-validation.md", "0007-auth-token-validation"],
  ["ADR-0008-security-ci-gates.md", "0008-security-ci-gates"],
  ["ADR-0009-permission-bitmap.md", "0009-permission-bitmap"],
  ["ADR-0010-cryptography-policy.md", "0010-cryptography-policy"],
  ["ADR-0011-proxy-auth-client.md", "0011-proxy-auth-client"],
  ["ADR-0012-proxy-request-normalization.md", "0012-proxy-request-normalization"],
  ["ADR-0013-proxy-input-validation-and-error-envelope.md", "0013-proxy-input-validation-and-error-envelope"],
  ["ADR-0014-core-domain-migration-sequencing.md", "0014-core-domain-migration-sequencing"],
  ["ADR-0015-proxy-rate-limit-skeleton.md", "0015-proxy-rate-limit-skeleton"],
  ["ADR-0016-agent-identity-verification.md", "0016-agent-identity-verification"],
  ["ADR-0017-request-id-strategy.md", "0017-request-id-strategy"],
  ["ADR-0018-graceful-shutdown.md", "0018-graceful-shutdown"],
  ["ADR-0019-opentelemetry-provider-configuration.md", "0019-opentelemetry-provider-configuration"],
  ["ADR-0020-shared-package-boundaries.md", "0020-shared-package-boundaries"],
  ["ADR-0021-prometheus-metric-catalog.md", "0021-prometheus-metric-catalog"],
  ["ADR-0022-health-check-contract.md", "0022-health-check-contract"],
  ["ADR-0023-docs-site-architecture.md", "0023-docs-site-architecture"],
]);

function adrHref(href) {
  const base = path.basename(href.replace(/\\/g, "/"));
  const slug = ADR_SLUGS.get(base);
  if (slug) return `/docs/adr/${slug}`;
  const match = base.match(/^ADR-(\d{4})-(.+)\.md$/i);
  if (match) return `/docs/adr/${match[1]}-${match[2].toLowerCase()}`;
  return null;
}

function tryAdrHref(normalized) {
  if (!normalized.includes("/adr/") && !normalized.startsWith("adr/")) return null;
  return adrHref(normalized);
}

function rewriteMarkdownFileLink(link, fileDir) {
  if (isAdrPath(link.pathPart)) {
    const adr = adrHref(link.pathPart);
    if (adr) return `[${link.text}](${adr}${link.hash ? `#${link.hash}` : ""})`;
  }

  const resolved = resolveRoadmapLinkTarget(link.pathPart, fileDir, tryAdrHref);
  return `[${link.text}](${resolved}${link.hash ? `#${link.hash}` : ""})`;
}

function fixMarkdownFileLinks(content, fileDir) {
  return rewriteMarkdownLinks(content, (link) =>
    rewriteMarkdownFileLink(link, fileDir),
  );
}

function fixLinks(content, fileDir) {
  let out = content;

  out = out.replaceAll("](../adr/", "](/docs/adr/");
  out = out.replaceAll("](adr/", "](/docs/adr/");
  out = out.replaceAll("`docs/roadmap/", "`docs/app/content/roadmap/");
  out = fixMarkdownFileLinks(out, fileDir);

  return out;
}

function fixGoalInFrontmatter(fm, fileDir) {
  const phase = fileDir.split("/")[0];
  const goalPrefix = "](../goals.md";
  const altPrefix = "(../goals.md";

  return fm
    .split("\n")
    .map((line) => {
      if (!line.startsWith("goal:")) return line;
      const raw = line.slice("goal:".length).trim();
      const val = readYamlValue(raw);
      const fixed = val
        .replaceAll(goalPrefix, `](/roadmap/${phase}/goals`)
        .replaceAll(altPrefix, `(/roadmap/${phase}/goals`);
      return `goal: ${JSON.stringify(fixed)}`;
    })
    .join("\n");
}

function readYamlValue(raw) {
  const trimmed = raw.trim();
  if (trimmed.startsWith('"')) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return trimmed.replace(/^"|"$/g, "");
    }
  }
  return trimmed.replace(/^"|"$/g, "");
}

function processMdxFile(abs, rel) {
  const fileDir = path.dirname(rel.replace(/\\/g, "/"));
  const raw = fs.readFileSync(abs, "utf8");
  const match = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
  if (!match) return;

  const dirForGoal = fileDir === "." ? "" : fileDir;
  const fm = fixGoalInFrontmatter(match[1], dirForGoal);
  const body = fixLinks(match[2], fileDir === "." ? "" : fileDir);
  fs.writeFileSync(abs, `---\n${fm}\n---\n${body}`, "utf8");
}

function walk(dir, relDir = "") {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const abs = path.join(dir, entry.name);
    const rel = relDir ? `${relDir}/${entry.name}` : entry.name;
    if (entry.isDirectory()) {
      walk(abs, rel.replace(/\/index\.mdx$/, ""));
      continue;
    }
    if (entry.name.endsWith(".mdx")) processMdxFile(abs, rel);
  }
}

walk(ROOT);
console.log("Fixed roadmap internal links");
