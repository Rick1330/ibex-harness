ifeq ($(OS),Windows_NT)
BASH := C:/Program Files/Git/bin/bash.exe
else
BASH := bash
endif

DEV_TOOL := infra/scripts/dev-tool.sh

.PHONY: help lint-docs security-scan repo-guards proto-lint proto-breaking proto-gen proto-test proto-test-integration test-integration coverage-report coverage-gate compose-dev-up compose-dev-down compose-dev-reset compose-dev-logs compose-dev-ps compose-test-up compose-test-down db-migrate db-migrate-down db-version db-seed db-repair-token-fks dev-smoke verify-phase15

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

proto-gen: ## Generate protobuf stubs locally (output gitignored)
	@"$(BASH)" "$(DEV_TOOL)" proto-gen

proto-test: ## Run protobuf contract unit tests
	@"$(BASH)" "$(DEV_TOOL)" proto-test

proto-test-integration: ## Run protobuf contract integration tests (requires buf)
	@"$(BASH)" "$(DEV_TOOL)" proto-test-integration

test-integration: ## Run all Go integration tests (-tags=integration)
	@"$(BASH)" "$(DEV_TOOL)" test-integration

coverage-report: ## Generate unit (+ integration if POSTGRES_TEST_DSN set) coverage report
	@"$(BASH)" infra/scripts/coverage-report.sh

coverage-gate: ## Fail if merged coverage profile is below MIN_COVERAGE (default 80)
	@"$(BASH)" infra/scripts/coverage-gate.sh coverage-go-merged.out

compose-dev-up: ## Start local development dependencies
	@"$(BASH)" "$(DEV_TOOL)" compose-dev-up

compose-dev-down: ## Stop local development dependencies
	@"$(BASH)" "$(DEV_TOOL)" compose-dev-down

compose-dev-reset: ## Stop dev stack and delete volumes (fresh Postgres data)
	@"$(BASH)" "$(DEV_TOOL)" compose-dev-reset

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

db-seed: ## Seed local dev database with test org, user, agent, and PAT
	@"$(BASH)" "$(DEV_TOOL)" db-seed

db-repair-token-fks: ## Fix orphaned token FKs after failed migration 008
	@"$(BASH)" "$(DEV_TOOL)" db-repair-token-fks

dev-smoke: ## Run local end-to-end smoke test (auth+proxy)
	@"$(BASH)" "$(DEV_TOOL)" dev-smoke

verify-phase15: ## Verify unified public site (IBEX_SITE_URL, default production)
	@"$(BASH)" "$(DEV_TOOL)" verify-phase15
