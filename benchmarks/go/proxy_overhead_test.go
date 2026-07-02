package gobench

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
