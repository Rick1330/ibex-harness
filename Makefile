SHELL := bash

PROTO_DIR := packages/proto
DEV_COMPOSE := infra/compose/dev/docker-compose.yml
DEV_ENV := infra/compose/dev/.env.example
TEST_COMPOSE := infra/compose/test/docker-compose.yml
PROTO_BREAKING_AGAINST := https://github.com/Rick1330/ibex-harness.git\#branch=main,subdir=packages/proto

.PHONY: help lint-docs security-scan repo-guards proto-lint proto-breaking compose-dev-up compose-dev-down compose-dev-logs compose-dev-ps compose-test-up compose-test-down

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "; print "IBEX Harness commands:"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

lint-docs: ## Run markdownlint using the repo configuration
	@npx --yes markdownlint-cli2 "**/*.md" "#node_modules"

security-scan: ## Run gitleaks locally if installed
	@command -v gitleaks >/dev/null 2>&1 || { echo "gitleaks is required for security-scan. Install it or rely on CI gitleaks."; exit 1; }
	@gitleaks detect --source . --config .gitleaks.toml --redact --verbose

repo-guards: ## Run repository layout and hygiene guards
	@bash .github/scripts/check-repo-layout.sh

proto-lint: ## Run Buf lint for protobuf contracts
	@command -v buf >/dev/null 2>&1 || { echo "buf is required for proto-lint. Install Buf CLI: https://buf.build/docs/installation"; exit 1; }
	@cd $(PROTO_DIR) && buf lint

proto-breaking: ## Run Buf breaking checks against main
	@command -v buf >/dev/null 2>&1 || { echo "buf is required for proto-breaking. Install Buf CLI: https://buf.build/docs/installation"; exit 1; }
	@cd $(PROTO_DIR) && buf breaking --against "$(PROTO_BREAKING_AGAINST)"

compose-dev-up: ## Start local development dependencies
	@command -v docker >/dev/null 2>&1 || { echo "docker is required for compose-dev-up."; exit 1; }
	@docker compose -f $(DEV_COMPOSE) --env-file $(DEV_ENV) up -d

compose-dev-down: ## Stop local development dependencies
	@command -v docker >/dev/null 2>&1 || { echo "docker is required for compose-dev-down."; exit 1; }
	@docker compose -f $(DEV_COMPOSE) --env-file $(DEV_ENV) down

compose-dev-logs: ## Tail local development dependency logs
	@command -v docker >/dev/null 2>&1 || { echo "docker is required for compose-dev-logs."; exit 1; }
	@docker compose -f $(DEV_COMPOSE) --env-file $(DEV_ENV) logs -f

compose-dev-ps: ## Show local development dependency status
	@command -v docker >/dev/null 2>&1 || { echo "docker is required for compose-dev-ps."; exit 1; }
	@docker compose -f $(DEV_COMPOSE) --env-file $(DEV_ENV) ps

compose-test-up: ## Start minimal test dependencies
	@command -v docker >/dev/null 2>&1 || { echo "docker is required for compose-test-up."; exit 1; }
	@docker compose -f $(TEST_COMPOSE) up -d

compose-test-down: ## Stop minimal test dependencies
	@command -v docker >/dev/null 2>&1 || { echo "docker is required for compose-test-down."; exit 1; }
	@docker compose -f $(TEST_COMPOSE) down
