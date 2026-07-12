#!/usr/bin/env bash
# Sync GitHub repository labels from .github/labels.json (colors + descriptions).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LABELS_FILE="${ROOT_DIR}/.github/labels.json"

if ! command -v gh >/dev/null 2>&1; then
  echo "sync-github-labels: gh CLI required"
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "sync-github-labels: node required"
  exit 1
fi

repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
echo "sync-github-labels: updating labels on ${repo}"

LABELS_FILE="$LABELS_FILE" node <<'NODE'
const { spawnSync } = require("child_process");
const fs = require("fs");

const labels = JSON.parse(fs.readFileSync(process.env.LABELS_FILE, "utf8"));
for (const label of labels) {
  const color = label.color.replace(/^#/, "");
  const result = spawnSync(
    "gh",
    [
      "label",
      "create",
      label.name,
      "--color",
      color,
      "--description",
      label.description ?? "",
      "--force",
    ],
    { stdio: "inherit" },
  );
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
  console.log(`ok: ${label.name} (#${color})`);
}
NODE

echo "sync-github-labels: done"
