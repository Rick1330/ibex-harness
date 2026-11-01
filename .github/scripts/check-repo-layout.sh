#!/usr/bin/env bash
set -euo pipefail

# Repository layout policy. `new findings/` and `test-results/` are local,
# gitignored scratch and are skipped below so the guard reflects the tracked tree.
ALLOWED_TOP='^(site|engineering|services|packages|infra|reports|benchmarks|patches|\.codescene|\.cursor|\.claude|\.opencode|\.github|\.git|_report|node_modules)$'
ROOT_DOCS='^(AGENTS\.md|CLAUDE\.md|README(\.(es|fr|de|pt-BR|zh-CN|ar))?\.md|LICENSE|CONTRIBUTING\.md|CODE_OF_CONDUCT\.md|CHANGELOG\.md)$'

fail=0

shopt -s nullglob
for entry in *; do
  if git check-ignore -q -- "$entry"; then
    continue
  fi
  if [[ -d "$entry" ]]; then
    if ! [[ "$entry" =~ $ALLOWED_TOP ]]; then
      echo "Disallowed top-level directory: $entry"
      fail=1
    fi
  elif [[ -f "$entry" ]]; then
    case "$entry" in
      .editorconfig|.gitattributes|.gitignore|.markdownlint-cli2.jsonc|.gitleaks.toml|.golangci.yml|.pre-commit-config.yaml|codecov.yml|.codacy.yml|.codacy.yaml|sonar-project.properties|.sonarcloud.properties|Makefile|go.mod|go.sum|osv-scanner.toml|package.json|pnpm-lock.yaml|pnpm-workspace.yaml|turbo.json|.nvmrc|LICENSE|AGENTS.md|CLAUDE.md|CODE_OF_CONDUCT.md|CONTRIBUTING.md|CHANGELOG.md|README.md|node_modules|version-release.config.json|.version-release-manifest.json) ;;
      *)
        if [[ "$entry" =~ \.md$ ]]; then
          if ! [[ "$entry" =~ $ROOT_DOCS ]]; then
            echo "Markdown at repo root not allowed: $entry (use engineering/)"
            fail=1
          fi
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
  if [[ "$f" =~ ^(services|packages|infra|benchmarks)/README\.md$ ]] || [[ "$f" =~ ^(services|packages|infra|benchmarks)/.+/README\.md$ ]] || [[ "$f" =~ ^(services|packages|infra|benchmarks)/.+/NOTICE\.md$ ]]; then
    continue
  fi
  if [[ "$f" == .github/* || "$f" == .claude/* || "$f" == .opencode/* ]]; then
    continue
  fi
  if [[ "$f" != site/* && "$f" != engineering/* && "$f" != benchmarks/* ]] && ! [[ "$f" =~ $ROOT_DOCS ]]; then
    echo "Doc outside allowed paths: $f"
    fail=1
  fi
done < <(git ls-files '*.md')

exit "$fail"
