package gobench

// Package gobench — proxy overhead stage microbenchmarks.
//
// PLACEHOLDER NOTICE (milestone 2.6.1):
// The stage* helpers below are SYNTHETIC stand-ins (hash / string work). They do
// NOT exercise real IBEX packages. The Phase 2 latency gate is green only after
// these are replaced with real calls. Do not implement full wiring here until
// the packages below exist and are importable from benchmarks/; until then keep
// this TODO matrix and leave placeholders.
//
// TODO matrix (replace synthetic stages → real packages):
//
//	| Synthetic          | Replace with                                      | Package / path              |
//	|--------------------|---------------------------------------------------|-----------------------------|
//	| stageAuth          | Auth cache hit path (LRU)                         | packages/authcache (2.2.1)  |
//	| stageRateLimit     | Limiter.Check                                     | packages/ratelimit          |
//	| stageDirectiveResolve | Directive resolve (Redis cache hit)            | proxy directive package     |
//	| stagePromptInject  | System-prompt / messages inject                   | proxy prompt inject (2.3.x) |
//	| BenchmarkProxyOverhead | Compose real stages + mock provider          | services/proxy + mock       |
//
// Also: k6 must hit POST /v1/chat/completions (full middleware), not /health.
// Pin baseline.json target_commit/baseline_sha only after a real 2.6.1 run.

import (
	"crypto/sha256"
	"encoding/hex"
	"strings"
	"testing"
)

func stageAuth() string {
	sum := sha256.Sum256([]byte("auth-token"))
	return hex.EncodeToString(sum[:8])
}

func stageRateLimit(key string) int {
	parts := strings.Split(key, "")
	return len(parts) * 3
}

func stageDirectiveResolve(v int) string {
	return strings.Repeat("directive:", v%5+1)
}

func stagePromptInject(s string) string {
	return "[system]" + s + "[/system]"
}

func BenchmarkStageAuth(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_ = stageAuth()
	}
}

func BenchmarkStageRateLimit(b *testing.B) {
	b.ReportAllocs()
	token := stageAuth()
	for i := 0; i < b.N; i++ {
		_ = stageRateLimit(token)
	}
}

func BenchmarkStageDirectiveResolve(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_ = stageDirectiveResolve(i)
	}
}

func BenchmarkStagePromptInject(b *testing.B) {
	b.ReportAllocs()
	input := stageDirectiveResolve(9)
	for i := 0; i < b.N; i++ {
		_ = stagePromptInject(input)
	}
}

func BenchmarkProxyOverhead(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		token := stageAuth()
		limit := stageRateLimit(token)
		dir := stageDirectiveResolve(limit)
		_ = stagePromptInject(dir)
	}
}
