#!/usr/bin/env bash
set -euo pipefail

ALLOWED_TOP='^(web|prompts|services|packages|infra|reports|benchmarks|\.github|\.git|\.cursor|_report|node_modules)$'
ROOT_DOCS='^(AGENTS\.md|PROMPTS\.md|README\.md|LICENSE|CONTRIBUTING\.md|CODE_OF_CONDUCT\.md|CHANGELOG\.md)$'

fail=0

shopt -s nullglob
for entry in *; do
  if [[ -d "$entry" ]]; then
    if ! [[ "$entry" =~ $ALLOWED_TOP ]]; then
      echo "Disallowed top-level directory: $entry"
      fail=1
    fi
  elif [[ -f "$entry" ]]; then
    case "$entry" in
      .cursorrules|.editorconfig|.gitattributes|.gitignore|.markdownlint-cli2.jsonc|.gitleaks.toml|.golangci.yml|.pre-commit-config.yaml|codecov.yml|.codacy.yml|.codacy.yaml|Makefile|go.mod|go.sum|osv-scanner.toml|package.json|pnpm-lock.yaml|pnpm-workspace.yaml|turbo.json|.nvmrc|LICENSE|AGENTS.md|CODE_OF_CONDUCT.md|CONTRIBUTING.md|CHANGELOG.md|PROMPTS.md|README.md|node_modules|version-release.config.json|.version-release-manifest.json) ;;
      *)
        if [[ "$entry" =~ \.md$ ]] && ! [[ "$entry" =~ $ROOT_DOCS ]]; then
          echo "Markdown at repo root not allowed: $entry (use web/engineering/)"
          fail=1
        else
          echo "Unexpected root file: $entry"
          fail=1
        fi
        ;;
    esac
  fi
done

while IFS= read -r f; do
  [[ "$f" == *.md ]] || continue
  if [[ "$f" =~ ^(services|packages|infra|benchmarks)/README\.md$ ]] || [[ "$f" =~ ^(services|packages|infra|benchmarks)/.+/README\.md$ ]]; then
    continue
  fi
  if [[ "$f" == .github/* ]]; then
    continue
  fi
  if [[ "$f" != web/* && "$f" != prompts/* && "$f" != benchmarks/* && "$f" != AGENTS.md && "$f" != PROMPTS.md && "$f" != README.md && "$f" != CONTRIBUTING.md && "$f" != CODE_OF_CONDUCT.md && "$f" != CHANGELOG.md ]]; then
    echo "Doc outside allowed paths: $f"
    fail=1
  fi
done < <(git ls-files '*.md')

exit "$fail"
