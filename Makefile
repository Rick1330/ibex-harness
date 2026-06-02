ifeq ($(OS),Windows_NT)
BASH := C:/Program Files/Git/bin/bash.exe
else
BASH := bash
endif

DEV_TOOL := infra/scripts/dev-tool.sh

.PHONY: help lint-docs security-scan repo-guards proto-lint proto-breaking compose-dev-up compose-dev-down compose-dev-logs compose-dev-ps compose-test-up compose-test-down db-migrate db-migrate-down db-version

help: ## Show available commands
	@"$(BASH)" "$(DEV_TOOL)" help

lint-docs: ## Run markdownlint using the repo configuration
	@"$(BASH)" "$(DEV_TOOL)" lint-docs

security-scan: ## Run gitleaks locally if installed
	@"$(BASH)" "$(DEV_TOOL)" security-scan

repo-guards: ## Run repository layout and hygiene guards
	@"$(BASH)" "$(DEV_TOOL)" repo-guards

proto-lint: ## Run Buf lint for protobuf contracts
	@"$(BASH)" "$(DEV_TOOL)" proto-lint

proto-breaking: ## Run Buf breaking checks against main
	@"$(BASH)" "$(DEV_TOOL)" proto-breaking

compose-dev-up: ## Start local development dependencies
	@"$(BASH)" "$(DEV_TOOL)" compose-dev-up

compose-dev-down: ## Stop local development dependencies
	@"$(BASH)" "$(DEV_TOOL)" compose-dev-down

compose-dev-logs: ## Tail local development dependency logs
	@"$(BASH)" "$(DEV_TOOL)" compose-dev-logs

compose-dev-ps: ## Show local development dependency status
	@"$(BASH)" "$(DEV_TOOL)" compose-dev-ps

compose-test-up: ## Start minimal test dependencies
	@"$(BASH)" "$(DEV_TOOL)" compose-test-up

compose-test-down: ## Stop minimal test dependencies
	@"$(BASH)" "$(DEV_TOOL)" compose-test-down

db-migrate: ## Apply all pending Postgres migrations
	@"$(BASH)" "$(DEV_TOOL)" db-migrate

db-migrate-down: ## Roll back one Postgres migration step
	@"$(BASH)" "$(DEV_TOOL)" db-migrate-down

db-version: ## Show current Postgres migration version
	@"$(BASH)" "$(DEV_TOOL)" db-version
