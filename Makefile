ifeq ($(OS),Windows_NT)
BASH := C:/Program Files/Git/bin/bash.exe
else
BASH := bash
endif

DEV_TOOL := infra/scripts/dev-tool.sh

.PHONY: help lint-docs lint-go security-scan repo-guards proto-lint proto-breaking proto-gen proto-test proto-test-integration test-integration test-embedder test-mcp-memory test-memory test-memory-integration test-worker test-worker-integration coverage-embedder-gate coverage-mcp-memory-gate coverage-memory-gate coverage-worker-gate memory-bench memory-bench-smoke coverage-report coverage-gate coverage-responsepipeline-gate compose-dev-up compose-dev-down compose-dev-reset compose-dev-logs compose-dev-ps compose-test-up compose-test-down observability-up observability-down observability-smoke observability-traffic observability-live-verify db-migrate db-migrate-down db-version db-seed db-repair-token-fks clickhouse-migrate clickhouse-migrate-down clickhouse-version dev-smoke dev-smoke-live e2e-wave2b-token-fks e2e-phase25 e2e-smoke-p3-memory verify-phase15 verify-phase25 mcp-conformance worker-dev worker-beat-dev worker-ping

help: ## Show available commands
	@"$(BASH)" "$(DEV_TOOL)" help

lint-docs: ## Run markdownlint using the repo configuration
	@"$(BASH)" "$(DEV_TOOL)" lint-docs

lint-go: ## Run golangci-lint on packages and Go services (depguard + base + complexity)
	@"$(BASH)" infra/scripts/ensure-origin-main.sh
	golangci-lint run --config .golangci.depguard.yml ./packages/...
	golangci-lint run --config .golangci.yml ./packages/... ./services/auth/... ./services/proxy/...
	golangci-lint run --config .golangci.complexity.yml ./packages/... ./services/auth/... ./services/proxy/...

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

test-embedder: ## Run Python embedder service unit tests (services/embedder)
	@"$(BASH)" infra/scripts/embedder-test-ci.sh

test-memory: ## Run Python memory service unit tests (services/memory)
	@"$(BASH)" infra/scripts/memory-test-ci.sh

test-memory-integration: ## Run memory PgVectorStore integration tests (needs Postgres + migrate)
	@"$(BASH)" infra/scripts/memory-integration-test-ci.sh

test-worker: ## Run Python worker service unit tests (services/worker)
	@"$(BASH)" infra/scripts/worker-test-ci.sh

test-worker-integration: ## Run worker Redis integration tests (needs Redis)
	@"$(BASH)" infra/scripts/worker-integration-test-ci.sh

memory-bench-smoke: ## Run memory HNSW bench at 10K (needs Postgres + migrate)
	@MEMORY_BENCH_SIZES="10000" "$(BASH)" infra/scripts/memory-bench.sh

memory-bench: ## Run memory HNSW benches at 10K/100K (needs Postgres + migrate; 1M is CI-only)
	@"$(BASH)" infra/scripts/memory-bench.sh

test-mcp-memory: ## Run Python mcp-memory service unit tests (services/mcp-memory)
	@"$(BASH)" infra/scripts/mcp-memory-test-ci.sh

test-clickhouse-migrate: ## Run ClickHouse migration unit tests (repo root; not from services/mcp-memory)
	@"$(BASH)" infra/scripts/clickhouse-migrate-test-ci.sh

test-clickhouse-migrate-integration: ## Run ClickHouse migration integration tests (requires compose-test ClickHouse)
	@"$(BASH)" infra/scripts/clickhouse-migrate-test-integration-ci.sh

coverage-embedder-gate: ## Fail if embedder app coverage is below MIN_COVERAGE (default 95)
	@"$(BASH)" infra/scripts/coverage-embedder-gate.sh

coverage-memory-gate: ## Fail if memory app coverage is below MIN_COVERAGE (default 90)
	@"$(BASH)" infra/scripts/coverage-memory-gate.sh

coverage-worker-gate: ## Fail if worker app coverage is below MIN_COVERAGE (default 90)
	@"$(BASH)" infra/scripts/coverage-worker-gate.sh

coverage-mcp-memory-gate: ## Fail if mcp-memory app coverage is below MIN_COVERAGE (default 90)
	@"$(BASH)" infra/scripts/coverage-mcp-memory-gate.sh

coverage-report: ## Generate unit (+ integration if POSTGRES_TEST_DSN set) coverage report
	@"$(BASH)" infra/scripts/coverage-report.sh

coverage-gate: ## Fail if merged coverage profile is below MIN_COVERAGE (default 80)
	@"$(BASH)" infra/scripts/coverage-gate.sh coverage-go-merged.out

coverage-responsepipeline-gate: ## Fail if scoped response-pipeline coverage is below MIN_COVERAGE (default 95)
	@"$(BASH)" infra/scripts/coverage-responsepipeline-gate_test.sh
	@"$(BASH)" infra/scripts/coverage-responsepipeline-gate.sh

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

observability-up: ## Start local LGTM observability stack (Prometheus/Grafana/Tempo/Loki)
	@"$(BASH)" infra/scripts/observability-up.sh

observability-down: ## Stop local LGTM observability stack
	@"$(BASH)" infra/scripts/observability-down.sh

observability-smoke: ## Smoke-check Grafana/Prometheus/Tempo/Loki (+ optional ibex_* series)
	@"$(BASH)" infra/scripts/observability-smoke.sh

observability-traffic: ## Hit local /health+/metrics so Prometheus has ibex_* series
	@"$(BASH)" infra/scripts/observability-traffic.sh

observability-live-verify: ## Start services, generate traffic, assert Grafana/Prometheus series
	@"$(BASH)" infra/scripts/observability-live-verify.sh

db-migrate: ## Apply all pending Postgres migrations
	@"$(BASH)" "$(DEV_TOOL)" db-migrate

db-migrate-down: ## Roll back one Postgres migration step
	@"$(BASH)" "$(DEV_TOOL)" db-migrate-down

db-version: ## Show current Postgres migration version
	@"$(BASH)" "$(DEV_TOOL)" db-version

db-seed: ## Seed local dev database with test org, user, agent, and PAT
	@"$(BASH)" "$(DEV_TOOL)" db-seed

db-repair-token-fks: ## Fix orphaned token FKs after failed migration 008/012
	@"$(BASH)" "$(DEV_TOOL)" db-repair-token-fks

clickhouse-migrate: ## Apply all pending ClickHouse migrations
	@"$(BASH)" "$(DEV_TOOL)" clickhouse-migrate

clickhouse-migrate-down: ## Roll back one ClickHouse migration step
	@"$(BASH)" "$(DEV_TOOL)" clickhouse-migrate-down

clickhouse-version: ## Show current ClickHouse migration version
	@"$(BASH)" "$(DEV_TOOL)" clickhouse-version

dev-smoke: ## Run local end-to-end smoke test (auth+proxy)
	@"$(BASH)" "$(DEV_TOOL)" dev-smoke

dev-smoke-live: ## Run live OpenRouter smoke test (auth+proxy+upstream)
	@"$(BASH)" "$(DEV_TOOL)" dev-smoke-live

e2e-wave2b-token-fks: ## Compose-dev Wave 2b token composite FK + CreateToken E2E
	@"$(BASH)" "$(DEV_TOOL)" e2e-wave2b-token-fks

verify-phase15: ## Verify unified public site (IBEX_SITE_URL, default production)
	@"$(BASH)" "$(DEV_TOOL)" verify-phase15

verify-phase25: ## Phase 2.5 exit gate verification (packages + Python services + optional e2e)
	@"$(BASH)" infra/scripts/verify_phase25.sh

e2e-phase25: ## Multi-service e2e (auth+proxy+embedder+mcp) against local processes
	@"$(BASH)" infra/scripts/e2e_phase25.sh

e2e-smoke-p3-memory: ## Phase 3 memory HTTP lifecycle e2e (compose-test stack)
	@"$(BASH)" infra/scripts/verify_phase3_memory_e2e.sh

mcp-conformance: ## MCP stub HTTP protocol checks (G6.M1 / exit criterion 7 evidence)
	@"$(BASH)" infra/scripts/mcp-conformance.sh

worker-dev: ## Run Celery worker locally (all queues; needs Redis)
	@cd services/worker && .venv/bin/celery -A app.celery_app:celery_app worker \
		-Q extraction,embedding,maintenance,mcp_audit --loglevel=info

worker-beat-dev: ## Run Celery beat locally (maintenance noop sweep; needs Redis)
	@cd services/worker && .venv/bin/celery -A app.celery_app:celery_app beat --loglevel=info

worker-ping: ## Celery inspect ping against local worker broker
	@cd services/worker && .venv/bin/celery -A app.celery_app:celery_app inspect ping --timeout=5
