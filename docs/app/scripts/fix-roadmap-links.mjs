#!/usr/bin/env node
/** Repair internal roadmap links for the public docs site. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

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

const FILE_RENAMES = new Map([
  ["PHASE1_EXIT_AUDIT.md", "phase1-exit-audit"],
  ["TEST_ARCHITECTURE.md", "test-architecture"],
  ["CI_AUDIT.md", "ci-audit"],
  ["MASTER_BRIEF.md", "master-brief"],
  ["CONTENT_SOURCES.md", "content-sources"],
  ["1.2.6-and-1.2.7-reqid-and-shutdown.md", "1.2.6-request-id-correlation-middleware"],
]);

function adrHref(href) {
  const base = path.basename(href.replace(/\\/g, "/"));
  const slug = ADR_SLUGS.get(base);
  if (slug) return `/docs/adr/${slug}`;
  const match = base.match(/^ADR-(\d{4})-(.+)\.md$/i);
  if (match) return `/docs/adr/${match[1]}-${match[2].toLowerCase()}`;
  return null;
}

function resolveRoadmapHref(href, fileDir) {
  const normalized = href.replace(/\\/g, "/");

  if (normalized.startsWith("http") || normalized.startsWith("/") || normalized.startsWith("#")) {
    return href;
  }

  if (normalized.includes("/adr/") || normalized.startsWith("adr/")) {
    const adr = adrHref(normalized);
    if (adr) return adr;
  }

  const special = new Map([
    ["CURRENT_STATE.md", "/roadmap/current-state"],
    ["FINDINGS.md", "/roadmap/findings"],
    ["PHASES.md", "/roadmap/overview"],
    ["../CURRENT_STATE.md", "/roadmap/current-state"],
    ["../FINDINGS.md", "/roadmap/findings"],
    ["../PHASES.md", "/roadmap/overview"],
    ["../../CURRENT_STATE.md", "/roadmap/current-state"],
    ["../../FINDINGS.md", "/roadmap/findings"],
  ]);
  if (special.has(normalized)) return special.get(normalized);

  let rel = normalized;
  if (rel.startsWith("./")) rel = rel.slice(2);
  if (rel.startsWith("../")) {
    const parts = fileDir.split("/").filter(Boolean);
    const segments = rel.split("/");
    for (const seg of segments) {
      if (seg === "..") parts.pop();
      else if (seg !== ".") parts.push(seg);
    }
    rel = parts.join("/");
  } else if (!rel.startsWith("phase-")) {
    rel = `${fileDir}/${rel}`.replace(/\/+/g, "/");
  }

  rel = rel.replace(/\\/g, "/");
  const base = path.basename(rel);
  if (FILE_RENAMES.has(base)) {
    rel = rel.replace(base, FILE_RENAMES.get(base));
  } else if (base === "README.md") {
    rel = rel.replace(/\/README\.md$/, "").replace(/README\.md$/, "");
    if (!rel) rel = fileDir;
  } else if (base.endsWith(".md")) {
    rel = rel.slice(0, -3);
  }

  rel = rel.replace(/\/index$/, "");
  return `/roadmap/${rel.replace(/^\/+/, "")}`;
}

function fixLinks(content, fileDir) {
  let out = content;

  out = out.replace(
    /\]\(([^)]*(?:\.\.\/)?adr\/ADR-\d{4}-[^)]+\.md)\)/gi,
    (_, href) => {
      const adr = adrHref(href);
      return adr ? `](${adr})` : `](${href})`;
    },
  );

  out = out.replace(/`docs\/roadmap\/([^`]+)`/g, (_, p) => {
    const cleaned = p.replace(/\.mdx?$/, "").replace(/README$/, "index");
    return "`docs/app/content/roadmap/" + cleaned + "`";
  });

  out = out.replace(/\[([^\]]*)\]\(([^)]+\.md(?:#[^)]*)?)\)/g, (match, text, href) => {
    const [pathPart, hash] = href.split("#");
    if (pathPart.includes("/adr/") || /^ADR-\d{4}/i.test(pathPart)) {
      const adr = adrHref(pathPart);
      if (adr) return `[${text}](${adr}${hash ? `#${hash}` : ""})`;
    }
    const resolved = resolveRoadmapHref(pathPart, fileDir);
    return `[${text}](${resolved}${hash ? `#${hash}` : ""})`;
  });

  return out;
}

function fixGoalInFrontmatter(fm, fileDir) {
  return fm.replace(/^goal:\s*(.+)$/m, (_, raw) => {
    const val = readYamlValue(raw);
    const fixed = val.replace(
      /\]\(\.\.\/goals\.md(#[^)]+)?\)/g,
      (_, hash) => `](/roadmap/${fileDir.split("/")[0]}/goals${hash ?? ""})`,
    );
    return `goal: ${JSON.stringify(fixed)}`;
  });
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

function walk(dir, relDir = "") {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const abs = path.join(dir, entry.name);
    const rel = relDir ? `${relDir}/${entry.name}` : entry.name;
    if (entry.isDirectory()) walk(abs, rel.replace(/\/index\.mdx$/, ""));
    else if (entry.name.endsWith(".mdx")) {
      const fileDir = path.dirname(rel.replace(/\\/g, "/"));
      const raw = fs.readFileSync(abs, "utf8");
      const match = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
      if (!match) continue;
      const dirForGoal = fileDir === "." ? "" : fileDir;
      const fm = fixGoalInFrontmatter(match[1], dirForGoal);
      const fixed = `---\n${fm}\n---\n${fixLinks(match[2], fileDir === "." ? "" : fileDir)}`;
      fs.writeFileSync(abs, fixed, "utf8");
    }
  }
}

walk(ROOT);
console.log("Fixed roadmap internal links");
